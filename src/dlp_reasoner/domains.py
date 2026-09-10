"""Versioned, strict scalar domains for opt-in rule/query operators.

Legacy RDF facts remain opaque. Only explicit operators decode these values.
Python implements the checked reference arithmetic; the native backend evaluates
whole typed batches without Python scalar callbacks. WGS84 geodesics use the same
native GeographicLib implementation in both modes, when that capability exists.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
import math
import re
from types import MappingProxyType
from typing import Any

from rdflib import Literal, URIRef
from rdflib.namespace import XSD

INT_MIN, INT_MAX = -(1 << 63), (1 << 63) - 1
SECOND = 1_000_000
DAY = 86400 * SECOND
TEMPORAL = "urn:dlp:temporal:"
NUMERIC = "urn:dlp:numeric:"
SPATIAL = "urn:dlp:spatial:"
PROFILE = "dlp-domains-v1"


class DomainError(ValueError):
    def __init__(self, code, message, *, operation=None, row=None):
        super().__init__(message)
        self.code, self.operation, self.row = code, operation, row


def _fail(code, message):
    raise DomainError(code, message)


def _int64(value):
    if type(value) is not int:
        _fail("TYPE_ERROR", "Expected an integer")
    if not INT_MIN <= value <= INT_MAX:
        _fail("OVERFLOW", "Integer exceeds signed 64-bit range")
    return value


@dataclass(frozen=True)
class IntegerValue:
    value: int

    def __post_init__(self):
        _int64(self.value)


@dataclass(frozen=True)
class DecimalValue:
    coefficient: int
    scale: int = 0

    def __post_init__(self):
        coefficient, scale = self.coefficient, self.scale
        if type(coefficient) is not int or type(scale) is not int or scale < 0:
            _fail("TYPE_ERROR", "Decimal needs an integer coefficient and nonnegative scale")
        if coefficient == 0:
            scale = 0
        while scale and coefficient and coefficient % 10 == 0:
            coefficient //= 10
            scale -= 1
        if scale > 18:
            _fail("INEXACT", "Decimal requires more than 18 fractional digits")
        _int64(coefficient)
        object.__setattr__(self, "coefficient", coefficient)
        object.__setattr__(self, "scale", scale)


@dataclass(frozen=True)
class FloatValue:
    value: float

    def __post_init__(self):
        if type(self.value) is not float or not math.isfinite(self.value):
            _fail("DOMAIN_ERROR", "Float input must be finite binary64")


@dataclass(frozen=True)
class DateValue:
    year: int
    month: int
    day: int

    def __post_init__(self):
        if any(type(v) is not int for v in (self.year, self.month, self.day)):
            _fail("TYPE_ERROR", "Calendar date fields must be integers")
        try:
            date(self.year, self.month, self.day)
        except ValueError as exc:
            _fail("DOMAIN_ERROR", str(exc))

    @property
    def ordinal(self):
        return date(self.year, self.month, self.day).toordinal()


@dataclass(frozen=True)
class InstantValue:
    microseconds: int

    def __post_init__(self):
        _int64(self.microseconds)


@dataclass(frozen=True)
class TimeValue:
    microseconds: int

    def __post_init__(self):
        _int64(self.microseconds)
        if not 0 <= self.microseconds < DAY:
            _fail("DOMAIN_ERROR", "Time of day must be within [00:00,24:00)")


@dataclass(frozen=True)
class DurationValue:
    microseconds: int

    def __post_init__(self):
        _int64(self.microseconds)


@dataclass(frozen=True)
class Point:
    longitude: float
    latitude: float
    crs: str = "EPSG:4326"
    revision: str = "wgs84-v1"

    def __post_init__(self):
        if (type(self.longitude) is not float or type(self.latitude) is not float
                or not math.isfinite(self.longitude) or not math.isfinite(self.latitude)
                or not -180 <= self.longitude <= 180 or not -90 <= self.latitude <= 90):
            _fail("DOMAIN_ERROR", "WGS84 point requires finite longitude ±180, latitude ±90")
        if self.crs != "EPSG:4326" or self.revision != "wgs84-v1":
            _fail("UNAVAILABLE", "Only the EPSG:4326/wgs84-v1 point profile is supported")


UNITS = ("urn:dlp:unit:metre", "urn:dlp:unit:second", "urn:dlp:unit:kmh")


@dataclass(frozen=True)
class Quantity:
    value: IntegerValue | DecimalValue
    unit: str

    def __post_init__(self):
        if type(self.value) not in (IntegerValue, DecimalValue):
            _fail("TYPE_ERROR", "Quantity requires a checked integer/decimal value")
        if self.unit not in UNITS:
            _fail("UNAVAILABLE", "Unknown quantity unit profile")


@dataclass(frozen=True)
class Interval:
    start: DateValue | InstantValue
    end: DateValue | InstantValue

    def __post_init__(self):
        if type(self.start) not in (DateValue, InstantValue) or type(self.start) is not type(self.end):
            _fail("TYPE_ERROR", "Interval endpoints must be two dates or two instants")
        if compare_values(self.start, self.end) >= 0:
            _fail("DOMAIN_ERROR", "Interval must have strictly positive length")


_VALUES = (IntegerValue, DecimalValue, FloatValue, DateValue, InstantValue,
           TimeValue, DurationValue, Point, Interval, Quantity)
_INTEGER_TYPES = {XSD.integer, XSD.long, XSD.int, XSD.short, XSD.byte,
                  XSD.nonNegativeInteger, XSD.positiveInteger, XSD.nonPositiveInteger,
                  XSD.negativeInteger, XSD.unsignedLong, XSD.unsignedInt,
                  XSD.unsignedShort, XSD.unsignedByte}
_INTEGER_BOUNDS = {
    XSD.long: (INT_MIN, INT_MAX), XSD.int: (-(1 << 31), (1 << 31) - 1),
    XSD.short: (-32768, 32767), XSD.byte: (-128, 127),
    XSD.nonNegativeInteger: (0, INT_MAX), XSD.positiveInteger: (1, INT_MAX),
    XSD.nonPositiveInteger: (INT_MIN, 0), XSD.negativeInteger: (INT_MIN, -1),
    XSD.unsignedLong: (0, INT_MAX), XSD.unsignedInt: (0, (1 << 32) - 1),
    XSD.unsignedShort: (0, 65535), XSD.unsignedByte: (0, 255),
}
_CLOCK = r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]+))?"
_DATETIME = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})T" + _CLOCK
                       + r"(Z|[+-][0-9]{2}:[0-9]{2})")
_DURATION = re.compile(r"(-)?P(?:([0-9]+)D)?(?:T(?:([0-9]+)H)?(?:([0-9]+)M)?"
                       r"(?:([0-9]+)(?:\.([0-9]+))?S)?)?")


def _fraction(text):
    text = text or ""
    if len(text) > 6:
        _fail("INEXACT", "Temporal fractional precision exceeds microseconds")
    return int(text.ljust(6, "0") or "0")


def _clock(hour, minute, second, fraction):
    hour, minute, second = int(hour), int(minute), int(second)
    if hour > 23 or minute > 59 or second > 59:
        _fail("DOMAIN_ERROR", "Invalid clock fields; leap seconds and 24:00 are unsupported")
    return ((hour * 60 + minute) * 60 + second) * SECOND + _fraction(fraction)


def decode(value):
    """Strict opt-in decoding; RDF lexical identity is not altered."""
    if type(value) in _VALUES:
        return value
    if type(value) is bool:
        return value
    if type(value) is int:
        return IntegerValue(value)
    if type(value) is float:
        return FloatValue(value)
    if type(value) is Decimal:
        return _decimal_text(str(value), allow_exponent=True)
    if not isinstance(value, Literal):
        _fail("TYPE_ERROR", "Expected an RDF literal or an immutable domain value")
    text, datatype = str(value), value.datatype
    # Bounded lexical inputs avoid giant integer/power allocation during validation.
    if len(text) > 4096:
        _fail("RESOURCE_LIMIT", "Domain literal exceeds the 4096-character decoding limit")
    if datatype in _INTEGER_TYPES:
        if not re.fullmatch(r"[+-]?[0-9]+", text):
            _fail("DOMAIN_ERROR", "Invalid integer lexical form")
        number = _int64(int(text))
        low, high = _INTEGER_BOUNDS.get(datatype, (INT_MIN, INT_MAX))
        if not low <= number <= high:
            _fail("DOMAIN_ERROR", "Integer does not belong to its declared subtype")
        return IntegerValue(number)
    if datatype == XSD.decimal:
        return _decimal_text(text)
    if datatype in (XSD.double, XSD.float):
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
            _fail("DOMAIN_ERROR", "Expected a finite floating-point lexical form")
        if datatype == XSD.float:
            _fail("UNAVAILABLE", "xsd:float binary32 conversion is not this binary64 capability")
        return FloatValue(float(text))
    if datatype == XSD.boolean:
        if text not in ("true", "false", "1", "0"):
            _fail("DOMAIN_ERROR", "Invalid Boolean lexical form")
        return text in ("true", "1")
    if datatype == XSD.date:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text):
            _fail("DOMAIN_ERROR", "Date requires YYYY-MM-DD without a timezone")
        return DateValue(*map(int, text.split("-")))
    if datatype in (XSD.dateTime, XSD.dateTimeStamp):
        match = _DATETIME.fullmatch(text)
        if not match:
            _fail("DOMAIN_ERROR", "Instant requires a full date/time and explicit offset")
        y, m, d, h, minute, s, fraction, zone = match.groups()
        calendar = DateValue(int(y), int(m), int(d))
        clock = _clock(h, minute, s, fraction)
        offset = 0
        if zone != "Z":
            hours, minutes = int(zone[1:3]), int(zone[4:6])
            if hours > 14 or minutes > 59 or (hours == 14 and minutes):
                _fail("DOMAIN_ERROR", "UTC offset exceeds ±14:00")
            offset = (hours * 60 + minutes) * 60 * SECOND * (1 if zone[0] == "+" else -1)
        return InstantValue((calendar.ordinal - date(1970, 1, 1).toordinal()) * DAY
                            + clock - offset)
    if datatype == XSD.time:
        match = re.fullmatch(_CLOCK, text)
        if not match:
            _fail("DOMAIN_ERROR", "Time of day requires a timezone-free HH:MM:SS value")
        return TimeValue(_clock(*match.groups()))
    if datatype in (XSD.dayTimeDuration, XSD.duration):
        match = _DURATION.fullmatch(text)
        if not match or not any(match.groups()[1:]) or text.endswith("T"):
            _fail("DOMAIN_ERROR", "Only fixed day/time durations are supported")
        sign, days, hours, minutes, seconds, fraction = match.groups()
        ticks = ((int(days or 0) * 24 + int(hours or 0)) * 60 + int(minutes or 0)) * 60
        ticks = (ticks + int(seconds or 0)) * SECOND + _fraction(fraction)
        return DurationValue(-ticks if sign else ticks)
    _fail("TYPE_ERROR", f"Unsupported literal datatype {datatype}")


def _decimal_text(text, allow_exponent=False):
    if len(text) > 4096:
        _fail("RESOURCE_LIMIT", "Decimal lexical input too long")
    pattern = r"([+-]?)([0-9]*)(?:\.([0-9]*))?"
    if allow_exponent:
        pattern += r"(?:[eE]([+-]?[0-9]+))?"
    match = re.fullmatch(pattern, text)
    if not match or not (match[2] or match[3]):
        _fail("DOMAIN_ERROR", "Invalid decimal lexical form")
    sign, whole, fraction = match[1], match[2], match[3] or ""
    exponent = int(match[4] or 0) if allow_exponent else 0
    digits = (whole + fraction).lstrip("0") or "0"
    scale = len(fraction) - exponent
    if digits == "0":
        return DecimalValue(0)
    while scale > 0 and digits.endswith("0"):
        digits = digits[:-1]
        scale -= 1
    if scale < 0:
        if len(digits) - scale > 19:
            _fail("OVERFLOW", "Decimal coefficient exceeds signed 64-bit range")
        digits += "0" * -scale
        scale = 0
    if len(digits) > 19:
        _fail("OVERFLOW", "Decimal coefficient exceeds signed 64-bit range")
    return DecimalValue(int(("-" if sign == "-" else "") + digits), scale)


def identity_key(value):
    """Hashable typed identity key, preserving the sign bit of binary64 zero."""
    if type(value) is float:
        return float, value.hex()
    if type(value) is FloatValue:
        return FloatValue, value.value.hex()
    if type(value) is Point:
        return Point, value.longitude.hex(), value.latitude.hex(), value.crs, value.revision
    return type(value), value


class DecodedCache:
    """Bounded identity-keyed side table; oversized lexical terms are never retained."""
    def __init__(self, max_entries=4096):
        if type(max_entries) is not int or max_entries < 0:
            raise ValueError("cache size must be a nonnegative integer")
        self.max_entries = max_entries
        self._values = OrderedDict()
        self.hits = self.misses = 0

    def decode(self, value):
        try:
            key = (PROFILE, identity_key(value))
            hash(key)
        except TypeError:
            return decode(value)
        if key in self._values:
            self.hits += 1
            self._values.move_to_end(key)
            return self._values[key]
        self.misses += 1
        result = decode(value)
        if self.max_entries:
            self._values[key] = result
            if len(self._values) > self.max_entries:
                self._values.popitem(last=False)
        return result

    def clear(self):
        self._values.clear()

    def __len__(self):
        return len(self._values)


def _number(value):
    if type(value) is IntegerValue:
        return Fraction(value.value)
    if type(value) is DecimalValue:
        return Fraction(value.coefficient, 10 ** value.scale)
    _fail("TYPE_ERROR", "Expected integer/decimal; float conversion must be explicit")


def value_key(value):
    value = decode(value)
    if type(value) in (IntegerValue, DecimalValue):
        return "numeric", _number(value)
    if type(value) is DateValue:
        return "date", value.ordinal
    if type(value) in (InstantValue, TimeValue, DurationValue):
        return type(value).__name__, value.microseconds
    if type(value) is FloatValue:
        return "float64", value.value
    if type(value) is bool:
        return "boolean", value
    if type(value) is Quantity:
        return "quantity:" + value.unit, _number(value.value)
    return type(value).__name__, value


def order_key(value):
    """(domain, ordered payload); a MIN group MUST check equal domain tags first."""
    key = value_key(value)
    if key[0] in ("Point", "Interval", "boolean"):
        _fail("TYPE_ERROR", "This value domain has no scalar ordering")
    return key


def compare_values(left, right):
    left, right = order_key(left), order_key(right)
    if left[0] != right[0]:
        _fail("TYPE_ERROR", "Cannot compare unrelated value domains")
    return (left[1] > right[1]) - (left[1] < right[1])


def _decimal_fraction(number):
    coefficient, denominator, scale = number.numerator, number.denominator, 0
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    scale = max(twos, fives)
    if denominator != 1 or scale > 18:
        _fail("INEXACT", "Quotient has no exact representation in decimal64/scale18")
    coefficient *= 2 ** (scale - twos) * 5 ** (scale - fives)
    return DecimalValue(coefficient, scale)


def _literal(value):
    if type(value) is bool:
        return Literal(value)
    if type(value) is IntegerValue:
        return Literal(str(value.value), datatype=XSD.integer, normalize=False)
    if type(value) is DecimalValue:
        digits = str(abs(value.coefficient)).rjust(value.scale + 1, "0")
        text = digits[:-value.scale] + "." + digits[-value.scale:] if value.scale else digits + ".0"
        return Literal(("-" if value.coefficient < 0 else "") + text,
                       datatype=XSD.decimal, normalize=False)
    if type(value) is FloatValue:
        return Literal(value.value, datatype=XSD.double)
    if type(value) is DateValue:
        return Literal(f"{value.year:04}-{value.month:02}-{value.day:02}",
                       datatype=XSD.date, normalize=False)
    if type(value) is InstantValue:
        try:
            timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
                microseconds=value.microseconds)
        except OverflowError:
            _fail("OVERFLOW", "Instant output exceeds the supported lexical year range")
        text = timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return Literal(text, datatype=XSD.dateTimeStamp, normalize=False)
    if type(value) is TimeValue:
        seconds, fraction = divmod(value.microseconds, SECOND)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return Literal(f"{h:02}:{m:02}:{s:02}.{fraction:06}", datatype=XSD.time, normalize=False)
    if type(value) is DurationValue:
        seconds, fraction = divmod(abs(value.microseconds), SECOND)
        text = ("-" if value.microseconds < 0 else "") + f"PT{seconds}.{fraction:06}S"
        return Literal(text, datatype=XSD.dayTimeDuration, normalize=False)
    return value


@dataclass(frozen=True)
class Operation:
    uri: str
    version: str
    input_types: tuple[str, ...]
    result_type: str
    required_positions: tuple[int, ...]
    determinism: str = "pure"
    dependencies: tuple[str, ...] = ()
    cardinality: str = "one"
    batches: bool = True
    opcode: int = 0

    @property
    def arity(self):
        return len(self.input_types)


@dataclass(frozen=True)
class DomainResult:
    value: Any = None
    error: DomainError | None = None

    @property
    def ok(self):
        return self.error is None


_SIGNATURES = (
    (TEMPORAL, "before", 1, ("temporal", "temporal"), "boolean"),
    (TEMPORAL, "after", 2, ("temporal", "temporal"), "boolean"),
    (TEMPORAL, "equal", 3, ("temporal", "temporal"), "boolean"),
    (TEMPORAL, "completedYears", 4, ("date", "date", "policy"), "integer"),
    (TEMPORAL, "interval", 5, ("endpoint", "endpoint"), "interval"),
    (TEMPORAL, "contains", 6, ("interval", "endpoint"), "boolean"),
    (TEMPORAL, "intersects", 7, ("interval", "interval"), "boolean"),
    (TEMPORAL, "meets", 8, ("interval", "interval"), "boolean"),
    (TEMPORAL, "add", 9, ("temporal", "duration"), "temporal"),
    (TEMPORAL, "elapsedSeconds", 10, ("instant", "instant"), "decimal"),
    *((NUMERIC, name, opcode, ("numeric", "numeric"), result) for opcode, name, result in (
        (20, "add", "numeric"), (21, "subtract", "numeric"), (22, "multiply", "numeric"),
        (23, "divide", "decimal"), (24, "equal", "boolean"), (25, "lessThan", "boolean"),
        (26, "lessThanOrEqual", "boolean"), (27, "greaterThan", "boolean"),
        (28, "greaterThanOrEqual", "boolean"))),
    (SPATIAL, "wgs84Point", 40, ("coordinate", "coordinate"), "point"),
    (SPATIAL, "wgs84Distance", 41, ("point", "point"), "float"),
    (SPATIAL, "dwithin", 42, ("point", "point", "coordinate"), "boolean"),
    (NUMERIC, "toFloat", 30, ("coordinate",), "float"),
    (NUMERIC, "floatLessThanOrEqual", 31, ("float", "float"), "boolean"),
    (NUMERIC, "quantity", 32, ("numeric", "unit"), "quantity"),
    (NUMERIC, "quantityAdd", 33, ("quantity", "quantity"), "quantity"),
    (NUMERIC, "quantitySubtract", 34, ("quantity", "quantity"), "quantity"),
    (NUMERIC, "quantityEqual", 35, ("quantity", "quantity"), "boolean"),
    (NUMERIC, "quantityLessThanOrEqual", 36, ("quantity", "quantity"), "boolean"),
    (NUMERIC, "quantityDivide", 37, ("quantity", "quantity"), "decimal"),
)
_TYPES = {"numeric": (IntegerValue, DecimalValue), "date": (DateValue,),
          "instant": (InstantValue,), "duration": (DurationValue,), "point": (Point,),
          "interval": (Interval,), "endpoint": (DateValue, InstantValue),
          "temporal": (DateValue, InstantValue, TimeValue, DurationValue),
          "coordinate": (IntegerValue, DecimalValue, FloatValue), "float": (FloatValue,),
          "quantity": (Quantity,)}


def _coordinate(value):
    number = value.value if type(value) is FloatValue else float(_number(value))
    if not math.isfinite(number):
        _fail("DOMAIN_ERROR", "Coordinate/radius is not finite")
    return number


class DomainRegistry:
    def __init__(self, backend="python", cache_size=4096, *, native_value_capacity=4096):
        if backend not in ("python", "native"):
            raise ValueError("Domain backend must be python or native")
        if type(native_value_capacity) is not int or not 4 <= native_value_capacity < 2**64:
            raise ValueError("native_value_capacity must be an integer from 4 to uint64 max")
        self.backend = backend
        self.cache = DecodedCache(cache_size)
        self.native_value_capacity = native_value_capacity
        self._native_context = None
        self._closed = False
        self.operations = MappingProxyType({ns + name: Operation(ns + name, "1", args, result,
                           tuple(range(len(args))), dependencies=("wgs84-v1",)
                           if ns == SPATIAL else (PROFILE,), opcode=opcode)
                           for ns, name, opcode, args, result in _SIGNATURES})

    def get(self, uri):
        uri = str(uri).replace("urn:dlp:proposed:", "urn:dlp:", 1)
        operation = self.operations.get(uri)
        if operation is None:
            raise DomainError("UNAVAILABLE", f"Unknown domain operation {uri}", operation=uri)
        return operation

    def decode(self, value):
        return self.cache.decode(value)

    def _arguments(self, operation, arguments):
        if not isinstance(arguments, Sequence) or isinstance(arguments, (str, bytes)):
            _fail("TYPE_ERROR", "Operation arguments must be a sequence of values")
        if len(arguments) != operation.arity:
            _fail("ARITY_ERROR", f"{operation.uri} requires {operation.arity} arguments")
        values = []
        for expected, argument in zip(operation.input_types, arguments):
            if expected == "unit":
                if not isinstance(argument, (str, URIRef, Literal)):
                    _fail("TYPE_ERROR", "Unit must be a URI or supported unit name")
                unit = str(argument).replace("urn:dlp:proposed:unit:", "urn:dlp:unit:")
                if unit in ("metre", "second", "kmh"):
                    unit = "urn:dlp:unit:" + unit
                if unit not in UNITS:
                    _fail("UNAVAILABLE", "Unknown quantity unit profile")
                values.append(unit)
                continue
            if expected == "policy":
                if str(argument) not in ("march1", "urn:dlp:calendar-policy:march1",
                                          "urn:dlp:proposed:calendar-policy:march1"):
                    _fail("UNAVAILABLE", "Only the march1 anniversary policy is supported")
                values.append("march1")
                continue
            value = self.decode(argument)
            if type(value) not in _TYPES[expected]:
                _fail("TYPE_ERROR", f"Expected {expected}, got {type(value).__name__}")
            values.append(value)
        return tuple(values)

    def evaluate(self, uri, arguments):
        result = self.evaluate_batch(uri, [arguments])[0]
        if result.error:
            raise result.error
        return result.value

    def native_stats(self):
        """Resident payload-transfer counters; no library is loaded just to inspect."""
        if self._native_context is None:
            return {"retained_values": 0, "capacity": self.native_value_capacity,
                    "transferred_inputs": 0, "transferred_outputs": 0, "evaluated_rows": 0,
                    "generation": 0, "intern_requests": 0, "intern_hits": 0, "clears": 0}
        return self._native_context.stats()

    def clear_native_values(self):
        if self._native_context is not None:
            self._native_context.clear()

    def close(self):
        if self._native_context is not None:
            self._native_context.close()
            self._native_context = None
        self.cache.clear()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def evaluate_batch(self, uri, rows):
        if self._closed:
            raise DomainError("UNAVAILABLE", "Domain registry is closed")
        operation = self.get(uri)
        results, valid, positions = [], [], []
        for index, row in enumerate(rows):
            try:
                values = self._arguments(operation, row)
                valid.append(values)
                positions.append(index)
                results.append(None)
            except DomainError as error:
                error.operation, error.row = operation.uri, index
                results.append(DomainResult(error=error))
        if valid:
            if self.backend == "native" or operation.opcode in (41, 42):
                from .domain_native import NativeDomainContext
                try:
                    if self._native_context is None:
                        self._native_context = NativeDomainContext(self.native_value_capacity)
                    computed = self._native_context.evaluate(operation.opcode, valid)
                except DomainError as error:
                    computed = [DomainResult(error=DomainError(error.code, str(error)))
                                for _ in valid]
            else:
                computed = []
                for row in valid:
                    try:
                        computed.append(DomainResult(_reference(operation.opcode, row)))
                    except DomainError as error:
                        computed.append(DomainResult(error=error))
            for index, result in zip(positions, computed):
                if result.error:
                    result.error.operation, result.error.row = operation.uri, index
                    results[index] = result
                else:
                    try:
                        results[index] = DomainResult(_literal(result.value))
                    except DomainError as error:
                        error.operation, error.row = operation.uri, index
                        results[index] = DomainResult(error=error)
        return tuple(results)


def _reference(opcode, values):
    if opcode == 30:
        return FloatValue(_coordinate(values[0]))
    a, b = values[:2]
    if opcode == 32:
        return Quantity(a, b)
    if 33 <= opcode <= 37:
        if a.unit != b.unit:
            _fail("TYPE_ERROR", "Quantity units differ; conversion must be explicit")
        operation = {33: 20, 34: 21, 35: 24, 36: 26, 37: 23}[opcode]
        result = _reference(operation, (a.value, b.value))
        return Quantity(result, a.unit) if opcode in (33, 34) else result
    if opcode == 31:
        return a.value <= b.value
    if opcode in (1, 2, 3):
        order = compare_values(a, b)
        return order < 0 if opcode == 1 else order > 0 if opcode == 2 else order == 0
    if opcode == 4:
        if b.ordinal < a.ordinal:
            _fail("DOMAIN_ERROR", "Child birth precedes parent birth")
        return IntegerValue(b.year - a.year - ((b.month, b.day) < (a.month, a.day)))
    if opcode == 5:
        return Interval(a, b)
    if opcode == 6:
        return compare_values(a.start, b) <= 0 and compare_values(b, a.end) < 0
    if opcode in (7, 8):
        compare_values(a.start, b.start)
        if opcode == 8:
            return compare_values(a.end, b.start) == 0
        return compare_values(a.start, b.end) < 0 and compare_values(b.start, a.end) < 0
    if opcode == 9:
        if type(a) is DateValue:
            if b.microseconds % DAY:
                _fail("DOMAIN_ERROR", "Date addition requires a whole-day duration")
            try:
                result = date.fromordinal(a.ordinal + b.microseconds // DAY)
            except ValueError:
                _fail("OVERFLOW", "Date addition exceeds years 1–9999")
            return DateValue(result.year, result.month, result.day)
        return type(a)(_int64(a.microseconds + b.microseconds))
    if opcode == 10:
        return _decimal_fraction(Fraction(b.microseconds - a.microseconds, SECOND))
    if 20 <= opcode <= 28:
        left, right = _number(a), _number(b)
        if opcode >= 24:
            return {24: left == right, 25: left < right, 26: left <= right,
                    27: left > right, 28: left >= right}[opcode]
        if opcode == 23 and not right:
            _fail("DOMAIN_ERROR", "Division by zero")
        result = {20: lambda: left + right, 21: lambda: left - right,
                  22: lambda: left * right, 23: lambda: left / right}[opcode]()
        if opcode != 23 and type(a) is IntegerValue and type(b) is IntegerValue:
            return IntegerValue(result.numerator)
        return _decimal_fraction(result)
    if opcode == 40:
        return Point(_coordinate(a), _coordinate(b))
    _fail("UNAVAILABLE", "Operation requires an unavailable implementation")


default_registry = DomainRegistry()


def evaluate(uri, arguments, *, backend="python"):
    return (default_registry if backend == "python" else DomainRegistry(backend)).evaluate(
        uri, arguments)


def evaluate_batch(uri, rows, *, backend="python"):
    return (default_registry if backend == "python" else DomainRegistry(backend)).evaluate_batch(
        uri, rows)
