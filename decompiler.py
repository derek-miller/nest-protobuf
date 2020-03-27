import functools
import logging
import multiprocessing as mp
import os
import re
import shutil
import string
import sys
from collections import OrderedDict
from typing import Any, Iterable, Optional, Sequence, Union

import jsbeautifier

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Missing traits:
# nest.trait.hvac.AirwaveSettingsTrait
# nest.trait.hvac.AirwaveTrait
# nest.trait.hvac.BackplateInfoTrait
# nest.trait.hvac.CoolSetPointScheduleSettingsTrait
# nest.trait.hvac.CoolToDrySettingsTrait
# nest.trait.hvac.CoolToDryTrait
# nest.trait.hvac.EcoModeSettingsTrait
# nest.trait.hvac.EcoModeTrait
# nest.trait.hvac.EmergencyHeatSettingsTrait
# nest.trait.hvac.FanControlCapabilitiesTrait
# nest.trait.hvac.FanControlSettingsTrait
# nest.trait.hvac.FilterReminderSettingsTrait
# nest.trait.hvac.HeatLinkSettingsTrait
# nest.trait.hvac.HeatLinkTrait
# nest.trait.hvac.HeatPumpControlSettingsTrait
# nest.trait.hvac.HeatPumpControlTrait
# nest.trait.hvac.HeatSetPointScheduleSettingsTrait
# nest.trait.hvac.HotWaterSettingsTrait
# nest.trait.hvac.HotWaterTrait
# nest.trait.hvac.HumidityControlSettingsTrait
# nest.trait.hvac.HvacDisplayTrait
# nest.trait.hvac.HvacEquipmentCapabilitiesTrait
# nest.trait.hvac.LeafTrait
# nest.trait.hvac.PreconditioningSettingsTrait
# nest.trait.hvac.PreconditioningTrait
# nest.trait.hvac.RadiantControlSettingsTrait
# nest.trait.hvac.RangeSetPointScheduleSettingsTrait
# nest.trait.hvac.SafetyShutoffCapabilitiesTrait
# nest.trait.hvac.SafetyTemperatureSettingsTrait
# nest.trait.hvac.ScheduleLearningSettingsTrait
# nest.trait.hvac.SunblockSettingsTrait
# nest.trait.hvac.SunblockTrait
# nest.trait.hvac.TargetTemperatureSettingsTrait
# nest.trait.hvac.TemperatureLockSettingsTrait
# nest.trait.hvac.TimeToTemperatureTrait

MIN_NAME_LENGTH = 10
TYPE_NAME_REMAPPING = {
    "ResourceId": ("weave.common.ResourceId", {"weave/common.proto"}),
    "ResourceName": ("weave.common.ResourceName", {"weave/common.proto"}),
    "DayOfWeek": ("weave.common.DayOfWeek", {"weave/common.proto"}),
    "MonthOfYear": ("weave.common.MonthOfYear", {"weave/common.proto"}),
    "TraitTypeId": ("weave.common.TraitTypeId", {"weave/common.proto"}),
    "TraitInstanceId": ("weave.common.TraitInstanceId", {"weave/common.proto"}),
    "FullTraitInstanceId": ("weave.common.FullTraitInstanceId", {"weave/common.proto"}),
    "ProfileSpecificStatusCode": (
        "weave.common.ProfileSpecificStatusCode",
        {"weave/common.proto"},
    ),
    "StringRef": ("weave.common.StringRef", {"weave/common.proto"}),
    "QuantityType": ("weave.common.QuantityType", {"weave/common.proto"}),
    "ResourceType": ("weave.common.ResourceType", {"weave/common.proto"}),
    "EventId": ("weave.common.EventId", {"weave/common.proto"}),
    "InterfaceName": ("weave.common.InterfaceName", {"weave/common.proto"}),
    "Timer": ("weave.common.Timer", {"weave/common.proto"}),
    "TimeOfDay": ("weave.common.TimeOfDay", {"weave/common.proto"}),
    "Timestamp": ("google.protobuf.Timestamp", {"google/protobuf/timestamp.proto"}),
    "Duration": ("google.protobuf.Duration", {"google/protobuf/duration.proto"}),
    "BoolValue": ("google.protobuf.BoolValue", {"google/protobuf/wrappers.proto"}),
    "Int32Value": ("google.protobuf.Int32Value", {"google/protobuf/wrappers.proto"}),
    "Int64Value": ("google.protobuf.Int64Value", {"google/protobuf/wrappers.proto"}),
    "UInt64Value": ("google.protobuf.UInt64Value", {"google/protobuf/wrappers.proto"}),
    "UInt32Value": ("google.protobuf.UInt32Value", {"google/protobuf/wrappers.proto"}),
    "StringValue": ("google.protobuf.StringValue", {"google/protobuf/wrappers.proto"}),
    "FloatValue": ("google.protobuf.FloatValue", {"google/protobuf/wrappers.proto"}),
    "Any": ("google.protobuf.Any", {"google/protobuf/any.proto"}),
    "FieldMask": ("google.protobuf.FieldMask", {"google/protobuf/field_mask.proto"}),
    "SchemaVersion": ("nest.messages.SchemaVersion", {"nest/messages.proto"}),
}


def get_files_in_dir(
    directory: str, extensions: Optional[Sequence[str]] = None
) -> Iterable[str]:
    if not os.path.isdir(directory):
        raise RuntimeError(f"Path is not a directory: {directory}")

    for dir_path, _, filenames in os.walk(directory):
        for filename in filenames:
            if not extensions or os.path.splitext(filename)[1] in extensions:
                yield os.path.join(dir_path, filename)


def beautify_js_file(in_path: str, out_dir: str, overwrite: bool = True) -> None:
    if not os.path.isfile(in_path):
        raise RuntimeError(f"Path is not a file: {in_path}")
    if not os.path.isdir(out_dir):
        raise RuntimeError(f"Path is not a directory: {out_dir}")

    out_path = os.path.join(out_dir, os.path.basename(in_path))
    if not overwrite and os.path.isfile(out_path):
        raise RuntimeError(f"File already exists: {out_path}")

    logger.debug("formatting '%s' -> '%s'", in_path, out_path)

    with open(in_path) as f:
        js = f.read()

    js = jsbeautifier.beautify(js)

    with open(out_path, "w+") as f:
        f.write(js)


def name_to_namespace(name: str) -> str:
    namespace = name.split(".")[0]
    assert namespace, "namespace cannot be empty"
    return namespace


def name_to_package(name: str) -> str:
    parts = name.split(".")
    package_parts = []
    for part in parts:
        if part[0] in string.ascii_uppercase:
            break
        package_parts.append(part)
    return ".".join(package_parts)


def name_to_nested_path(name: str, kind: str) -> Sequence[str]:
    assert kind in ("message", "enum"), f"unknown kind {kind}"

    package = name_to_package(name)
    assert package, "package cannot be empty"

    parts = name.split(package)[1].strip(".").split(".")
    assert parts, "name only includes package name"

    last_part = parts.pop()

    return (
        [package]
        + (["__messages__"] if parts else [])
        + parts
        + [f"__{kind}s__", last_part]
    )


def nested_set(obj: dict, *keys: str, value: Any) -> None:
    p = obj
    for key in keys[:-1]:
        p = p.setdefault(key, OrderedDict())

    p[keys[-1]] = value


def nested_get(
    obj, *keys: Union[str, int], default: Any = None, raise_error: bool = False
) -> Any:
    for key in keys:
        try:
            obj = obj[key]
        except (KeyError, TypeError, IndexError):
            if raise_error:
                raise
            return default
    return obj


def strip_suffix(val, suffix):
    return re.sub(f"{re.escape(suffix)}$", "", val)


def sub_values(value: str, *replaces: str, replacement: str = "") -> str:
    for replace in replaces:
        value = value.replace(replace, replacement)
    return value


def parse_to_object(input_lines, idx, packages, message, field_numbers_to_type):
    field_with_default_re = re.compile(
        r"getFieldWithDefault\([^,]+,\s*(\d+),\s*([^)]+)\)"
    )
    object_list_re = re.compile(r"toObjectList\([^,]+,\s*[^.]+\.(.+)\.toObject")
    object_map_re = re.compile(r"toObject\([^,]+,\s*[^.]+\.(.+)\.toObject")
    object_re = re.compile(r"[a-zA-Z]+\.([a-zA-Z0-9_.]+)\.toObject")
    generic_map_re = re.compile(r" [a-zA-Z]+\.toObject\([^,]+,\s*void 0\)")
    field_re = re.compile(r"Message\.getField\([^,]+,\s*(\d+)\)")
    repeated_field_re = re.compile(r"Message\.getRepeatedField\([^,]+,\s*(\d+)\)")
    opt_floating_point_field_re = re.compile(
        r"Message\.getOptionalFloatingPointField\([^,]+,\s*(\d+)\)"
    )
    repeating_floating_point_field_re = re.compile(
        r"Message\.getRepeatedFloatingPointField\([^,]+,\s*(\d+)\)"
    )

    fields = []
    while True:
        idx += 1
        line = input_lines[idx].strip()
        if line.endswith("};"):
            break

        if line.count(":") > 0:
            field_name, field_meta = re.split(r":\s*", line, 1)
            field_with_default_match = field_with_default_re.search(field_meta)
            object_list_match = object_list_re.search(field_meta)
            object_map_match = object_map_re.search(field_meta)
            object_match = object_re.search(field_meta)
            generic_map_match = generic_map_re.search(field_meta)
            field_match = field_re.search(field_meta)
            repeated_field_match = repeated_field_re.search(field_meta)
            opt_floating_point_field_match = opt_floating_point_field_re.search(
                field_meta
            )
            repeating_floating_point_field_match = repeating_floating_point_field_re.search(
                field_meta
            )

            # A few exceptions to the name rules.
            if field_name == "faultList":
                field_name = "fault"
            if field_name == "pb_extends":
                field_name = "extends"

            if field_with_default_match:
                field_type, field_number = field_numbers_to_type[message][field_name]
            elif object_list_match:
                field_name = strip_suffix(field_name, "List")
                field_type, field_number = field_numbers_to_type[message][field_name]
                field_type = f"repeated {field_type}"
            elif object_map_match:
                field_name = strip_suffix(field_name, "Map")
                field_type, field_number = field_numbers_to_type[message][field_name]
            elif object_match:
                field_type, field_number = field_numbers_to_type[message][field_name]
            elif generic_map_match:
                field_name = strip_suffix(field_name, "Map")
                field_type, field_number = field_numbers_to_type[message][field_name]
            elif opt_floating_point_field_match:
                field_type, field_number = field_numbers_to_type[message][field_name]
            elif repeating_floating_point_field_match:
                field_name = strip_suffix(field_name, "List")
                field_type, field_number = field_numbers_to_type[message][field_name]
                field_type = f"repeated {field_type}"
            elif repeated_field_match:
                field_name = strip_suffix(field_name, "List")
                field_type, field_number = field_numbers_to_type[message][field_name]
                field_type = f"repeated {field_type}"
            elif field_match:
                field_type, field_number = field_numbers_to_type[message][field_name]
            elif "List_asB64()" in field_meta:
                field_name = strip_suffix(field_name, "List")
                field_type, field_number = field_numbers_to_type[message][field_name]
                field_type = f"repeated {field_type}"
            elif "_asB64()" in field_meta:
                field_type, field_number = field_numbers_to_type[message][field_name]
            else:
                raise Exception()

            fields.append((field_number, field_type, field_name))

    fields.sort()
    logger.debug("%s has %s field(s)", message, len(fields) or "no")
    nested_set(
        packages, *name_to_nested_path(message, "message"), "__fields__", value=fields
    )
    package = name_to_package(message)
    nested_set(
        packages,
        package,
        "__imports__",
        value=nested_get(field_numbers_to_type, package, "__imports__", default=set()),
    )


def _parse_to_enum(input_lines, idx, packages, message):
    enums = []
    while True:
        idx += 1
        line = input_lines[idx].strip()
        if line.startswith("}"):
            break
        enum_name, enum_value = re.split(r"\s*:\s*", line)
        enum_value = int(float(enum_value.split(",")[0].upper()))
        enums.append((enum_value, enum_name))

    enums.sort()
    logger.debug("%s has %s enum value(s)", message, len(enums) or "no")
    nested_set(
        packages,
        *name_to_nested_path(message, "enum"),
        value=OrderedDict((enum_name, enum_value) for enum_value, enum_name in enums),
    )


def _parse_types_and_numbers(input_lines, idx, data, name):
    object_re = re.compile(r"= new [a-zA-Z0-9]+\.([^,;]+)[,;]")
    map_re = re.compile(
        r"\.Map\.deserializeBinary\([^,]+,[^,]+,\s*([^,]+),\s*([^,]+),\s*(?:proto\.)?([^,]+),"
    )
    field_re = re.compile(r"[a-zA-Z]+\.set([^(]+)\([a-zA-Z]+\)[;,]")
    list_re = re.compile(r"[a-zA-Z]+\.add([^(]+)\([a-zA-Z]+\)[;,]")
    map_field_re = re.compile(r"[a-zA-Z]+\.get([^(]+)\(\)[;,]")
    while True:
        idx += 1
        line = input_lines[idx].strip()
        if line.startswith("return "):
            break
        if line.startswith("case "):
            field_number = int(line.split(" ")[1].strip(":"))
            field_type = None
            field_name = None
            while line != "break;":
                idx += 1
                line = input_lines[idx].strip()
                object_match = object_re.search(line)
                map_match = map_re.search(line)
                field_match = field_re.search(line)
                list_match = list_re.search(line)
                map_field_match = map_field_re.search(line)
                if field_match:
                    field_name = strip_suffix(field_match.group(1), "List")
                    field_name = field_name[0].lower() + field_name[1:]
                elif list_match:
                    field_name = list_match.group(1)
                    field_name = field_name[0].lower() + field_name[1:]
                elif map_field_match:
                    field_name = strip_suffix(map_field_match.group(1), "Map")
                    field_name = field_name[0].lower() + field_name[1:]

                if field_name and field_type:
                    break

                if field_type:
                    continue

                if ".readBool()" in line:
                    field_type = "bool"
                elif ".readEnum()" in line:
                    field_type = "UNKNOWN_ENUM"
                elif ".readPackedEnum()" in line:
                    field_type = "UNKNOWN_ENUM"
                elif ".readDouble()" in line:
                    field_type = "double"
                elif ".readFloat()" in line:
                    field_type = "float"
                elif ".readString()" in line or ".readUint64String()" in line:
                    field_type = "string"
                elif ".readPackedUint64String()" in line:
                    field_type = "string"
                elif ".readBytes()" in line:
                    field_type = "bytes"
                elif ".readUint32()" in line:
                    field_type = "uint32"
                elif ".readPackedUint32()" in line:
                    field_type = "uint32"
                elif ".readUint64()" in line:
                    field_type = "uint64"
                elif ".readPackedUint64()" in line:
                    field_type = "uint64"
                elif ".readInt32()" in line:
                    field_type = "int32"
                elif ".readPackedInt32()" in line:
                    field_type = "int32"
                elif ".readInt64()" in line:
                    field_type = "int64"
                elif ".readSint32()" in line:
                    field_type = "sint32"
                elif ".readSint64()" in line:
                    field_type = "sint64"
                elif object_match:
                    field_type = object_match.group(1)
                elif map_match:
                    field_type_k = map_match.group(1)
                    field_type_v = map_match.group(2)
                    field_type_v_message = map_match.group(3)
                    if ".readString" in field_type_k:
                        field_type_k = "string"
                    elif ".readUint32" in field_type_k:
                        field_type_k = "uint32"
                    elif ".readUint64" in field_type_k:
                        field_type_k = "uint64"
                    else:
                        raise Exception()
                    if ".readString" in field_type_v:
                        field_type_v = "string"
                    elif ".readUint32" in field_type_v:
                        field_type_v = "uint32"
                    elif ".readMessage" in field_type_v:
                        field_type_v_message = strip_suffix(
                            field_type_v_message, ".deserializeBinaryFromReader"
                        )
                        field_type_v = field_type_v_message
                    else:
                        raise Exception()
                    field_type = f"map<{field_type_k}, {field_type_v}>"

            assert field_type
            assert field_number
            assert field_name

            field_type, required_imports = TYPE_NAME_REMAPPING.get(
                field_type, (field_type, set())
            )
            package = name_to_package(name)
            nested_set(
                data,
                package,
                "__imports__",
                value=nested_get(data, package, "__imports__", default=set())
                | required_imports,
            )
            nested_set(data, name, field_name, value=(field_type, field_number))


def _write_package(f, package_name, package):
    assert "__fields__" not in package, "packages cannot contain top level fields"

    f.write('syntax = "proto3";\n\n')

    imports = sorted(list(package.get("__imports__", set())))
    for i in imports:
        f.write(f'import "{i}";\n')
    if imports:
        f.write("\n")

    f.write(f"package {package_name};\n\n")

    enums = package.get("__enums__", {})
    _write_enums(f, enums)

    messages = package.get("__messages__", {})
    if enums and messages:
        f.write("\n")
    _write_messages(f, messages, current_path=package_name)


def _write_messages(f, messages, indent="", current_path=""):
    num_messages = len(messages)
    for i, (message_name, message_data) in enumerate(messages.items()):
        _write_message(
            f, message_name, message_data, indent=indent, current_path=current_path
        )
        if i + 1 != num_messages:
            f.write("\n")


def _write_message(f, message_name, message_value, indent="", current_path=""):
    f.write(f"{indent}message {message_name} {{\n")

    fields = message_value.get("__fields__", [])
    for field_number, field_type, field_name in fields:
        f.write(
            f"{indent}    {sub_values(field_type, current_path + '.', message_name + '.')} {field_name} = {field_number};\n"
        )

    enums = message_value.get("__enums__", {})
    if fields and enums:
        f.write("\n")
    _write_enums(f, enums, indent="    ")

    messages = message_value.get("__messages__", {})
    if enums and messages or fields and messages:
        f.write("\n")
    _write_messages(
        f, messages, indent="    ", current_path=f"{current_path}.{message_name}"
    )

    f.write(f"{indent}}}\n")


def _write_enums(f, enums, indent=""):
    num_enums = len(enums)
    for i, (enum_name, enum_values) in enumerate(enums.items()):
        _write_enum(f, enum_name, enum_values, indent=indent)
        if i + 1 != num_enums:
            f.write("\n")


def _write_enum(f, enum_name, enum_values, indent=""):
    f.write(f"{indent}enum {enum_name} {{\n")
    for name, value in enum_values.items():
        f.write(f"{indent}    {name} = {value};\n")
    f.write(f"{indent}}}\n")


def _write_proto_files(data, out_dir: str, overwrite: bool = True) -> None:
    out_dir_exists = os.path.isdir(out_dir)
    if not overwrite and out_dir_exists:
        raise RuntimeError(f"Directory already exists: {out_dir}")
    elif overwrite and out_dir_exists:
        logger.warning("deleting '%s' in order to regenerate proto files", out_dir)
        shutil.rmtree(out_dir)

    logger.info("writing proto files to '%s'", out_dir)
    for package, package_data in data.items():
        filename = os.path.join(out_dir, *package.split(".")) + ".proto"
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        logger.debug("writing '%s'", filename)
        with open(filename, "w+") as f:
            _write_package(f, package, package_data)


def main():
    assert len(sys.argv) == 2 and os.path.isdir(
        sys.argv[1]
    ), "must pass directory to web page source files"
    current_dir = os.path.dirname(__file__)
    raw_js_dir = os.path.abspath(sys.argv[1])
    formatted_js_dir = os.path.join(current_dir, ".cache", "formatted-js-source")
    generated_proto_dir = os.path.join(current_dir, "nest-protobuf-generated")
    skip_namespaces = ("google",)

    # Format the source code to make it easier to find patterns.
    if not os.path.exists(formatted_js_dir):
        os.mkdir(formatted_js_dir)
        pool = mp.Pool(mp.cpu_count())
        logger.info("formatting js files in '%s'", formatted_js_dir)
        pool.map(
            functools.partial(beautify_js_file, out_dir=formatted_js_dir),
            get_files_in_dir(raw_js_dir, extensions=(".js",)),
        )
        pool.close()

    input_lines = []
    logger.info("reading formatted js files in '%s'", formatted_js_dir)
    for path in get_files_in_dir(formatted_js_dir, extensions=(".js",)):
        logger.debug("reading '%s'", path)
        with open(path) as f:
            input_lines.extend(f.readlines())

    field_numbers_to_type = {}
    binary_reader_re = re.compile(
        r" proto\.([a-zA-Z0-9._]+)(?!\.prototype)\.deserializeBinaryFromReader\s+=\s+function"
    )
    logger.info("extracting field types and numbers from source")
    for idx, s in enumerate(input_lines):
        s = s.strip()

        if len(s) < MIN_NAME_LENGTH:
            continue

        binary_reader_match = binary_reader_re.search(s)
        if binary_reader_match:
            name = binary_reader_match.group(1)
            if name_to_namespace(name) in skip_namespaces:
                continue
            logger.debug("extracting %s", name)
            _parse_types_and_numbers(input_lines, idx, field_numbers_to_type, name)
            continue

    data = {}
    object_re = re.compile(
        r" proto\.([a-zA-Z0-9._]+)(?!\.prototype)\.toObject\s+=\s+function"
    )
    enum_re = re.compile(r" proto\.([a-zA-Z0-9._]+)(?!\.prototype)\s+=\s+{$")
    logger.info("extracting message types and enums from source")
    for idx, s in enumerate(input_lines):
        s = s.strip()

        if len(s) < MIN_NAME_LENGTH:
            continue

        object_match = object_re.search(s)
        if object_match:
            name = object_match.group(1)
            if name_to_namespace(name) in skip_namespaces:
                continue
            logger.debug("extracting type %s", name)
            parse_to_object(input_lines, idx, data, name, field_numbers_to_type)
            continue

        enum_match = enum_re.search(s)
        if enum_match:
            name = enum_match.group(1)
            if name_to_namespace(name) in skip_namespaces:
                continue
            logger.debug("extracting enum %s", name)
            _parse_to_enum(input_lines, idx, data, name)
            continue

    data = OrderedDict(sorted(data.items(), key=lambda i: i[0]))
    _write_proto_files(data, out_dir=generated_proto_dir)


if __name__ == "__main__":
    main()
