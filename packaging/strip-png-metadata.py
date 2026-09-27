"""Remove PNG text/EXIF metadata without decoding or changing image pixels."""
import struct
import sys
from pathlib import Path


def strip_metadata(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a PNG")
    result = bytearray(data[:8])
    offset = 8
    while offset < len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + size + 12
        if end > len(data):
            raise ValueError("Truncated PNG")
        if data[offset + 4:offset + 8] not in {b"tEXt", b"zTXt", b"iTXt", b"eXIf"}:
            result.extend(data[offset:end])
        offset = end
    path.write_bytes(result)


if __name__ == "__main__":
    strip_metadata(Path(sys.argv[1]))
