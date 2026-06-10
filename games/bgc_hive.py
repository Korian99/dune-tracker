"""
Read unencrypted Flutter Hive boxes from Board Games Companion (BGC) backups.

Binary layout follows Hive v2.2.x (isar/hive): each frame is
uint32 length (includes length field + body + crc32), uint8 key type, key,
value, uint32 crc32 over all preceding frame bytes.

BGC registers its core model adapters at upstream typeId + 32; enum adapters
keep their source type ids (also +32 in practice for types registered after
the offset migration — playthrough status is 37 = 5 + 32).

Field layouts match generated adapters in Progrunning/BoardGamesCompanion.
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Hive FrameValueType (hive/lib/src/binary/frame.dart)
NULL = 0
INT = 1
DOUBLE = 2
BOOL = 3
STRING = 4
BYTE_LIST = 5
INT_LIST = 6
DOUBLE_LIST = 7
BOOL_LIST = 8
STRING_LIST = 9
LIST = 10
MAP = 11
HIVE_LIST = 12
# Hive DateTimeWithTimezone adapter (micros + isUtc); BGC stores epoch ms in the int slot.
DATE_TIME = 18

# Frame key types
KEY_UINT = 0
KEY_STRING = 1

# BGC custom object type ids (upstream HiveBoxes + 32)
TYPE_PLAYER = 34
TYPE_PLAYTHROUGH = 35
TYPE_SCORE = 36
TYPE_PLAYTHROUGH_NOTE = 50  # 18 + 32
TYPE_NO_SCORE_GAME_RESULT = 53  # 21 + 32
TYPE_SCORE_GAME_RESULT = 56  # 24 + 32

# Enum type ids in backup (+32 vs hive_boxes.dart)
ENUM_PLAYTHROUGH_STATUS = 37  # 5 + 32
ENUM_COOPERATIVE_RESULT = 54  # 22 + 32
ENUM_SCORE_TIEBREAKER = 57  # 25 + 32

ENUM_LABELS: dict[int, dict[int, str]] = {
    ENUM_PLAYTHROUGH_STATUS: {0: "started", 1: "finished"},
    ENUM_COOPERATIVE_RESULT: {0: "win", 1: "loss"},
    ENUM_SCORE_TIEBREAKER: {0: "shared", 1: "place"},
}

_CRC_TABLE = (
    0x00000000, 0x77073096, 0xEE0E612C, 0x990951BA, 0x076DC419, 0x706AF48F,
    0xE963A535, 0x9E6495A3, 0x0EDB8832, 0x79DCB8A4, 0xE0D5E91E, 0x97D2D988,
    0x09B64C2B, 0x7EB17CBD, 0xE7B82D07, 0x90BF1D91, 0x1DB71064, 0x6AB020F2,
    0xF3B97148, 0x84BE41DE, 0x1ADAD47D, 0x6DDDE4EB, 0xF4D4B551, 0x83D385C7,
    0x136C9856, 0x646BA8C0, 0xFD62F97A, 0x8A65C9EC, 0x14015C4F, 0x63066CD9,
    0xFA0F3D63, 0x8D080DF5, 0x3B6E20C8, 0x4C69105E, 0xD56041E4, 0xA2677172,
    0x3C03E4D1, 0x4B04D447, 0xD20D85FD, 0xA50AB56B, 0x35B5A8FA, 0x42B2986C,
    0xDBBBC9D6, 0xACBCF940, 0x32D86CE3, 0x45DF5C75, 0xDCD60DCF, 0xABD13D59,
    0x26D930AC, 0x51DE003A, 0xC8D75180, 0xBFD06116, 0x21B4F4B5, 0x56B3C423,
    0xCFBA9599, 0xB8BDA50F, 0x2802B89E, 0x5F058808, 0xC60CD9B2, 0xB10BE924,
    0x2F6F7C87, 0x58684C11, 0xC1611DAB, 0xB6662D3D, 0x76DC4190, 0x01DB7106,
    0x98D220BC, 0xEFD5102A, 0x71B18589, 0x06B6B51F, 0x9FBFE4A5, 0xE8B8D433,
    0x7807C9A2, 0x0F00F934, 0x9609A88E, 0xE10E9818, 0x7F6A0DBB, 0x086D3D2D,
    0x91646C97, 0xE6635C01, 0x6B6B51F4, 0x1C6C6162, 0x856530D8, 0xF262004E,
    0x6C0695ED, 0x1B01A57B, 0x8208F4C1, 0xF50FC457, 0x65B0D9C6, 0x12B7E950,
    0x8BBEB8EA, 0xFCB9887C, 0x62DD1DDF, 0x15DA2D49, 0x8CD37CF3, 0xFBD44C65,
    0x4DB26158, 0x3AB551CE, 0xA3BC0074, 0xD4BB30E2, 0x4ADFA541, 0x3DD895D7,
    0xA4D1C46D, 0xD3D6F4FB, 0x4369E96A, 0x346ED9FC, 0xAD678846, 0xDA60B8D0,
    0x44042D73, 0x33031DE5, 0xAA0A4C5F, 0xDD0D7CC9, 0x5005713C, 0x270241AA,
    0xBE0B1010, 0xC90C2086, 0x5768B525, 0x206F85B3, 0xB966D409, 0xCE61E49F,
    0x5EDEF90E, 0x29D9C998, 0xB0D09822, 0xC7D7A8B4, 0x59B33D17, 0x2EB40D81,
    0xB7BD5C3B, 0xC0BA6CAD, 0xEDB88320, 0x9ABFB3B6, 0x03B6E20C, 0x74B1D29A,
    0xEAD54739, 0x9DD277AF, 0x04DB2615, 0x73DC1683, 0xE3630B12, 0x94643B84,
    0x0D6D6A3E, 0x7A6A5AA8, 0xE40ECF0B, 0x9309FF9D, 0x0A00AE27, 0x7D079EB1,
    0xF00F9344, 0x8708A3D2, 0x1E01F268, 0x6906C2FE, 0xF762575D, 0x806567CB,
    0x196C3671, 0x6E6B06E7, 0xFED41B76, 0x89D32BE0, 0x10DA7A5A, 0x67DD4ACC,
    0xF9B9DF6F, 0x8EBEEFF9, 0x17B7BE43, 0x60B08ED5, 0xD6D6A3E8, 0xA1D1937E,
    0x38D8C2C4, 0x4FDFF252, 0xD1BB67F1, 0xA6BC5767, 0x3FB506DD, 0x48B2364B,
    0xD80D2BDA, 0xAF0A1B4C, 0x36034AF6, 0x41047A60, 0xDF60EFC3, 0xA867DF55,
    0x316E8EEF, 0x4669BE79, 0xCB61B38C, 0xBC66831A, 0x256FD2A0, 0x5268E236,
    0xCC0C7795, 0xBB0B4703, 0x220216B9, 0x5505262F, 0xC5BA3BBE, 0xB2BD0B28,
    0x2BB45A92, 0x5CB36A04, 0xC2D7FFA7, 0xB5D0CF31, 0x2CD99E8B, 0x5BDEAE1D,
    0x9B64C2B0, 0xEC63F226, 0x756AA39C, 0x026D930A, 0x9C0906A9, 0xEB0E363F,
    0x72076785, 0x05005713, 0x95BF4A82, 0xE2B87A14, 0x7BB12BAE, 0x0CB61B38,
    0x92D28E9B, 0xE5D5BE0D, 0x7CDCEFB7, 0x0BDBDF21, 0x86D3D2D4, 0xF1D4E242,
    0x68DDB3F8, 0x1FDA836E, 0x81BE16CD, 0xF6B9265B, 0x6FB077E1, 0x18B74777,
    0x88085AE6, 0xFF0F6A70, 0x66063BCA, 0x11010B5C, 0x8F659EFF, 0xF862AE69,
    0x616BFFD3, 0x166CCF45, 0xA00AE278, 0xD70DD2EE, 0x4E048354, 0x3903B3C2,
    0xA7672661, 0xD06016F7, 0x4969474D, 0x3E6E77DB, 0xAED16A4A, 0xD9D65ADC,
    0x40DF0B66, 0x37D83BF0, 0xA9BCAE53, 0xDEBB9EC5, 0x47B2CF7F, 0x30B5FFE9,
    0xBDBDF21C, 0xCABAC28A, 0x53B39330, 0x24B4A3A6, 0xBAD03605, 0xCDD70693,
    0x54DE5729, 0x23D967BF, 0xB3667A2E, 0xC4614AB8, 0x5D681B02, 0x2A6F2B94,
    0xB40BBE37, 0xC30C8EA1, 0x5A05DF1B, 0x2D02EF8D,
)


def _hive_crc(data: bytes, offset: int = 0, length: int | None = None, crc: int = 0) -> int:
    crc ^= 0xFFFFFFFF
    end = offset + (length if length is not None else len(data) - offset)
    for i in range(offset, end):
        crc = _CRC_TABLE[(crc ^ data[i]) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def _epoch_to_datetime(raw: int, is_utc: bool) -> datetime:
    """BGC backups store epoch milliseconds in the DateTime adapter int slot."""
    if abs(raw) >= 10**14:
        seconds = raw / 1_000_000
    else:
        seconds = raw / 1_000
    tz = timezone.utc if is_utc else None
    return datetime.fromtimestamp(seconds, tz=tz)


class HiveReader:
    def __init__(self, data: bytes, offset: int = 0, limit: int | None = None):
        self.data = data
        self.offset = offset
        self.limit = len(data) if limit is None else limit

    def _need(self, n: int) -> None:
        if self.offset + n > self.limit:
            raise EOFError(self.offset)

    def read_byte(self) -> int:
        self._need(1)
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_uint32(self) -> int:
        self._need(4)
        value = struct.unpack_from("<I", self.data, self.offset)[0]
        self.offset += 4
        return value

    def read_int(self) -> int:
        self._need(8)
        value = int(struct.unpack_from("<d", self.data, self.offset)[0])
        self.offset += 8
        return value

    def read_double(self) -> float:
        self._need(8)
        value = struct.unpack_from("<d", self.data, self.offset)[0]
        self.offset += 8
        return value

    def read_bool(self) -> bool:
        return self.read_byte() > 0

    def read_string(self) -> str:
        length = self.read_uint32()
        self._need(length)
        value = self.data[self.offset : self.offset + length].decode("utf-8")
        self.offset += length
        return value

    def read_key(self) -> str | int:
        key_type = self.read_byte()
        if key_type == KEY_UINT:
            return self.read_uint32()
        if key_type == KEY_STRING:
            length = self.read_byte()
            self._need(length)
            key = self.data[self.offset : self.offset + length].decode("utf-8")
            self.offset += length
            return key
        raise ValueError(f"Unsupported frame key type {key_type}")

    def read_enum(self, type_id: int) -> str | int:
        index = self.read_byte()
        labels = ENUM_LABELS.get(type_id)
        if labels and index in labels:
            return labels[index]
        return index

    def read_custom_object(self, type_id: int) -> dict[str, Any]:
        field_count = self.read_byte()
        fields: dict[int, Any] = {}
        for _ in range(field_count):
            index = self.read_byte()
            fields[index] = self.read()
        return {"_typeId": type_id, "fields": fields}

    def read(self, type_id: int | None = None) -> Any:
        if type_id is None:
            type_id = self.read_byte()
        if type_id == NULL:
            return None
        if type_id == INT:
            return self.read_int()
        if type_id == DOUBLE:
            return self.read_double()
        if type_id == BOOL:
            return self.read_bool()
        if type_id == STRING:
            return self.read_string()
        if type_id == BYTE_LIST:
            length = self.read_uint32()
            self._need(length)
            blob = bytes(self.data[self.offset : self.offset + length])
            self.offset += length
            return blob
        if type_id == INT_LIST:
            length = self.read_uint32()
            return [self.read_int() for _ in range(length)]
        if type_id == DOUBLE_LIST:
            length = self.read_uint32()
            return [self.read_double() for _ in range(length)]
        if type_id == BOOL_LIST:
            length = self.read_uint32()
            return [self.read_bool() for _ in range(length)]
        if type_id == STRING_LIST:
            length = self.read_uint32()
            return [self.read_string() for _ in range(length)]
        if type_id == LIST:
            length = self.read_uint32()
            return [self.read() for _ in range(length)]
        if type_id == MAP:
            length = self.read_uint32()
            return {self.read(): self.read() for _ in range(length)}
        if type_id == HIVE_LIST:
            length = self.read_uint32()
            box_len = self.read_byte()
            self._need(box_len)
            box_name = self.data[self.offset : self.offset + box_len].decode("ascii")
            self.offset += box_len
            keys = [self.read_key() for _ in range(length)]
            return {"_hiveList": box_name, "keys": keys}
        if type_id == DATE_TIME:
            raw = self.read_int()
            is_utc = self.read_bool()
            return _epoch_to_datetime(raw, is_utc)
        if type_id in ENUM_LABELS:
            return self.read_enum(type_id)
        if type_id >= 32:
            return self.read_custom_object(type_id)
        raise ValueError(f"Unsupported Hive type {type_id} at offset {self.offset}")


def read_box(path: str | Path) -> dict[str | int, Any]:
    """Parse a .hive file; last frame per key wins (Hive append semantics)."""
    data = Path(path).read_bytes()
    store: dict[str | int, Any] = {}
    pos = 0
    while pos + 4 <= len(data):
        start = pos
        frame_len = struct.unpack_from("<I", data, pos)[0]
        if frame_len < 8 or start + frame_len > len(data):
            break
        stored_crc = struct.unpack_from("<I", data, start + frame_len - 4)[0]
        if _hive_crc(data, start, frame_len - 4) != stored_crc:
            raise ValueError(f"CRC mismatch in {path} at offset {start}")
        reader = HiveReader(data, start + 4, start + frame_len - 4)
        key = reader.read_key()
        if reader.offset < start + frame_len - 4:
            store[key] = reader.read()
        else:
            store.pop(key, None)
        pos = start + frame_len
    return store


def _fields(obj: dict[str, Any] | None) -> dict[int, Any]:
    if not obj or "_typeId" not in obj:
        return {}
    raw = obj.get("fields")
    return raw if isinstance(raw, dict) else {}


def _score_points(fields: dict[int, Any]) -> float | None:
    legacy = fields.get(4)
    if isinstance(legacy, str) and legacy.strip():
        try:
            return float(legacy)
        except ValueError:
            pass
    result = fields.get(6)
    if isinstance(result, dict):
        rf = _fields(result)
        points = rf.get(0)
        if points is not None:
            return float(points)
    return None


def _score_placement(fields: dict[int, Any]) -> int | None:
    result = fields.get(6)
    if isinstance(result, dict):
        rf = _fields(result)
        place = rf.get(1)
        if place is not None:
            return int(place)
    return None


def decode_player(obj: dict[str, Any]) -> dict[str, str] | None:
    if obj.get("_typeId") != TYPE_PLAYER:
        return None
    f = _fields(obj)
    player_id = f.get(0)
    name = f.get(1)
    if not player_id or not name:
        return None
    if f.get(3):
        return None
    return {"id": str(player_id), "name": str(name).strip()}


def decode_playthrough(obj: dict[str, Any]) -> dict[str, Any] | None:
    """
    Playthrough @HiveField order (playthrough.g.dart write order):
      0 id, 1 boardGameId, 4 startDate, 5 endDate, 6 status, 7 isDeleted,
      8 bggPlayId, 2 playerIds, 3 scoreIds, 9 notes
    """
    if obj.get("_typeId") != TYPE_PLAYTHROUGH:
        return None
    f = _fields(obj)
    if f.get(7):
        return None
    start = f.get(4)
    end = f.get(5)
    played_at = end or start
    duration_minutes = None
    if isinstance(start, datetime) and isinstance(end, datetime):
        s = start if start.tzinfo else start.replace(tzinfo=timezone.utc)
        e = end if end.tzinfo else end.replace(tzinfo=timezone.utc)
        duration_minutes = max(0, int((e - s).total_seconds() // 60))
    return {
        "id": f.get(0),
        "board_game_id": str(f.get(1) or ""),
        "player_ids": list(f.get(2) or []),
        "score_ids": list(f.get(3) or []),
        "start_date": start,
        "end_date": end,
        "played_at": played_at,
        "duration_minutes": duration_minutes,
        "status": f.get(6),
        "bgg_play_id": f.get(8),
        "notes": f.get(9) or [],
    }


def decode_score(obj: dict[str, Any]) -> dict[str, Any] | None:
    """
    Score @HiveField order (score.g.dart write order):
      0 id, 2 playerId, 3 boardGameId, 4 value (legacy str), 1 playthroughId,
      5 noScoreGameResult, 6 scoreGameResult (points, place, tiebreaker)
    """
    if obj.get("_typeId") != TYPE_SCORE:
        return None
    f = _fields(obj)
    return {
        "id": f.get(0),
        "playthrough_id": f.get(1),
        "player_id": f.get(2),
        "board_game_id": str(f.get(3) or ""),
        "value": f.get(4),
        "victory_points": _score_points(f),
        "placement": _score_placement(f),
        "no_score_game_result": f.get(5),
        "score_game_result": f.get(6),
    }


def load_players(path: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for obj in read_box(path).values():
        if not isinstance(obj, dict):
            continue
        player = decode_player(obj)
        if player:
            out[player["id"]] = player["name"]
    return out


def load_playthroughs(path: str | Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obj in read_box(path).values():
        if not isinstance(obj, dict):
            continue
        pt = decode_playthrough(obj)
        if pt and pt.get("id"):
            out.append(pt)
    return out


def load_scores(path: str | Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for obj in read_box(path).values():
        if not isinstance(obj, dict):
            continue
        score = decode_score(obj)
        if score and score.get("id"):
            out.append(score)
    return out


if __name__ == "__main__":
    import json
    import sys

    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_bgc_backup_extract")
    players = load_players(base / "players.hive")
    playthroughs = load_playthroughs(base / "playthroughs.hive")
    scores = load_scores(base / "scores.hive")

    print(f"players: {len(players)}")
    print(f"playthroughs: {len(playthroughs)}")
    print(f"scores: {len(scores)}")

    if playthroughs:
        sample_id = playthroughs[0]["id"]
        sample_scores = [s for s in scores if s.get("playthrough_id") == sample_id]
        print("\nSample playthrough:")
        print(json.dumps(playthroughs[0], default=str, indent=2))
        print(f"\nScores for playthrough ({len(sample_scores)}):")
        for row in sample_scores[:5]:
            print(json.dumps(row, default=str, indent=2))
