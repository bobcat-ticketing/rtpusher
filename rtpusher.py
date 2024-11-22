"""
Realtime data simulator device based on MQTT
"""

import argparse
import asyncio
import datetime
import json
import logging
import time

import aiomqtt
import pendulum
import pynmea2
import yaml
from cryptojwt.utils import b64d, b64e

FILE_PREFIX = "FILE_"
BASE64_PREFIX = "BASE64_"

previous_dt = None


def decdeg2dms(dd, dirpos, dirneg):
    direction = dirpos if dd >= 0 else dirneg
    (minutes, seconds) = divmod(abs(dd) * 3600, 60)
    (degrees, minutes) = divmod(minutes, 60)
    if dirpos == "N":
        return f"{degrees:02.0f}{minutes:02.0f}.{seconds:02.0f}", direction
    else:
        return f"{degrees:03.0f}{minutes:02.0f}.{seconds:02.0f}", direction


def contents_to_nmea(contents: dict):
    global previous_dt
    if "timestamp" in contents:
        dt = pendulum.parse(contents["timestamp"])
    elif "duration" in contents and previous_dt is not None:
        duration = pendulum.parse(contents["duration"])
        dt = previous_dt + duration
    else:
        dt = datetime.datetime.utcnow()
    previous_dt = dt
    lat, lat_dir = decdeg2dms(contents["lat"], "N", "S")
    lon, lon_dir = decdeg2dms(contents["long"], "E", "W")
    posdata = {"lat": lat, "lat_dir": lat_dir, "lon": lon, "lon_dir": lon_dir}
    posdata["timestamp"] = dt.time().strftime("%H%M%S")
    posdata["datestamp"] = dt.date().strftime("%d%m%y")
    posdata["status"] = "A"
    pos = []
    for field in pynmea2.RMC.fields:
        pos.append(posdata.get(field[1], ""))
    return str(pynmea2.RMC("GP", "RMC", pos))


def get_channel_contents(config: dict, name: str, contents: dict):
    """Publish channel contents on MQTT"""
    if name in config:
        channel_topic = config[name]["topic"]
        channel_format = config[name]["format"]
        if channel_format == "json":
            new_contents = {}
            for key, value in contents.items():
                if key.startswith(FILE_PREFIX):
                    key = key[len(FILE_PREFIX) :]
                    with open(value, "rb") as input_file:
                        value = input_file.read()
                    if key.startswith(BASE64_PREFIX):
                        key = key[len(BASE64_PREFIX) :]
                        value = b64e(value)
                    value = value.decode()
                new_contents[key] = value
            payload = json.dumps(new_contents).encode()
        elif channel_format == "nmea":
            payload = contents_to_nmea(contents).encode()
        elif channel_format == "bytes":
            if "base64" in contents:
                payload = b64d(contents["base64"])
            elif "file" in contents:
                filename = contents["file"]
                with open(filename, "rb") as input_file:
                    payload = input_file.read()
            elif "string" in contents:
                payload = contents["string"].encode()
            else:
                raise Exception("No binary contents found")
        else:
            raise Exception(f"Undefined format: {channel_format}")
        return (channel_topic, payload)
    else:
        raise Exception(f"Undefined channel: {name}")


async def send_realtime(client: aiomqtt.Client, data: list):
    for topic, msg in data:
        ret = await client.publish(topic, msg)
        logging.debug("Published to MQTT topic %s -> %s", topic, ret)


def match_response(expect: dict, data_format: str, data: bytes):
    if data_format == "json":
        data_dict = json.loads(data.decode())
    else:
        logging.error("Unsupported format: %s", data_format)
        return False
    if expect is None:
        logging.error("Unexpected data")
        return False
    for key, value in expect.items():
        if key in data_dict:
            if value != data_dict[key]:
                logging.error(
                    "Expect mismatch for %s: expected %s, got %s",
                    key,
                    value,
                    data_dict[key],
                )
                return False
        else:
            logging.error("Missing data %s", key)
            return False
    return True


async def process_yaml(data: dict, client: aiomqtt.Client, speed: float = 1.0):
    """Process YAML realtime data"""
    channel_config = data.get("mqtt_publish", {})
    _timeout = data.get("timeout", 3.0)
    sub = []
    subscribed_channels = {}
    for name, channel in data.get("mqtt_subscribe", {}).items():
        logging.debug("Subscribe to: %s -> %s", name, channel)
        sub.append((channel["topic"], channel.get("qos", 1)))
        subscribed_channels[channel["topic"]] = name, channel.get("format", "json")
    if sub:
        ret = await client.subscribe(sub)
        logging.debug("MQTT subscribe: %s", ret)
    errors = 0
    for tentry in data["testdata"]:
        logging.info("ID: %s", tentry["id"])
        messages = []
        has_time = False
        for channel_name, channel_contents in tentry["content"].items():
            (topic, payload) = get_channel_contents(
                channel_config, channel_name, channel_contents
            )
            logging.debug("Topic %s, Payload %s", topic, payload)
            msg = (topic, payload)
            # Make sure we send time first
            if channel_name == "time":
                messages.insert(0, msg)
                has_time = True
            elif channel_name == "gps" and not has_time:
                messages.insert(0, msg)
            else:
                messages.append(msg)
        ret = await send_realtime(client, messages)
        logging.info("Sent %s", ", ".join(tentry["content"]))
        if "expect" in tentry:
            expected = tentry["expect"]
            try:
                while expected:
                    async with client.messages() as messages:
                        async for message in messages:
                            message_channel, message_format = subscribed_channels[
                                message.topic.value
                            ]
                            expect = expected[message_channel]
                            if match_response(expect, message_format, message.payload):
                                logging.debug(
                                    "Got expected result on channel %s", message_channel
                                )
                                del expected[message_channel]
                            else:
                                logging.error(
                                    "Got unexpected result on channel %s = %s",
                                    message_channel,
                                    message.payload,
                                )
                                errors += 1
            except asyncio.TimeoutError:
                logging.error(
                    "Didn't receive expected result from channel(s): %s",
                    ", ".join(expected),
                )
                errors += len(expected)
        if speed != 0:
            delay = tentry.get("sleep", 0) / speed
            if delay > 0:
                logging.info("Sleeping for %f seconds", delay)
                time.sleep(delay)
    if errors > 0:
        logging.error("Test finished with %d errors", errors)
    else:
        logging.info("Test finished OK!")


async def process_csv(filename: str, client: aiomqtt.Client, speed: float = 1.0):
    """Process CSV realtime data"""
    with open(filename) as testdata_file:
        _ = testdata_file.readline()
        last_timestamp = None
        for line in testdata_file:
            (timestamp, topic, qos, message) = line.rstrip().split(",")
            topic = topic.strip()
            message = message.strip()
            payload = b64d(message)
            if last_timestamp is not None and speed != 0:
                delay = (float(timestamp) - float(last_timestamp)) / speed
                if delay > 0:
                    logging.info("Sleeping for %f seconds", delay)
                    time.sleep(delay)
            logging.info("Topic %s, Payload %s", topic, message)
            asyncio.get_event_loop().run_until_complete(
                send_realtime(client, [(topic, payload)])
            )
            last_timestamp = timestamp


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="MQTT based realtime data simulator")

    parser.add_argument(
        "--server",
        dest="server",
        metavar="server",
        help="MQTT broker",
        default="127.0.0.1",
    )
    parser.add_argument(
        "--speed",
        dest="speed",
        metavar="factor",
        help="Speed factor",
        type=float,
        default=1,
    )
    parser.add_argument(
        "--loop", dest="loop", action="store_true", default=False, help="Loop forever"
    )
    parser.add_argument(
        "--debug", dest="debug", action="store_true", help="Enable debugging"
    )
    parser.add_argument(
        "--format",
        dest="format",
        choices=["yaml", "csv"],
        default="yaml",
        help="Input data format",
    )
    parser.add_argument("filename", metavar="filename", help="Testdata file")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    async with aiomqtt.Client(hostname=args.server) as client:
        logging.debug("MQTT connect to %s", args.server)
        if args.format == "yaml":
            with open(args.filename) as testdata_file:
                data = yaml.safe_load(testdata_file)
            await process_yaml(client=client, data=data, speed=args.speed)
        elif args.format == "csv":
            await process_csv(client=client, filename=args.filename, speed=args.speed)
        else:
            raise Exception("Unknown format")


def cli():
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
