from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import json
import os


@dataclass
class VaccinationPoint:
    name: str
    latitude: float
    longitude: float
    radius_km: float = 2.0


@dataclass
class VaccineBox:
    box_code: str
    product: str
    quantity: int


@dataclass
class Waybill:
    waybill_id: str
    vehicle_plate: str
    route: str
    carrier: str
    departure_time: datetime
    outbound_order_time: datetime
    vaccination_point: VaccinationPoint
    vaccine_boxes: list = field(default_factory=list)


@dataclass
class TrajectoryPoint:
    timestamp: datetime
    latitude: float
    longitude: float
    speed: float = 0.0


@dataclass
class Trajectory:
    waybill_id: str
    points: list = field(default_factory=list)


@dataclass
class TemperatureRecord:
    timestamp: datetime
    temperature: float


@dataclass
class TemperatureLog:
    waybill_id: str
    interval_minutes: int
    records: list = field(default_factory=list)
    range_min: float = 2.0
    range_max: float = 8.0


@dataclass
class BoxCheck:
    box_code: str
    checked: bool
    photo: Optional[str] = None


@dataclass
class Receipt:
    waybill_id: str
    recipient: str
    received_at: datetime
    signed: bool
    signature_photo: Optional[str] = None
    box_checks: list = field(default_factory=list)
    anomaly_note: Optional[str] = None


@dataclass
class ValidationIssue:
    waybill_id: str
    category: str
    severity: str
    message: str


@dataclass
class LoadResult:
    success: bool
    error_message: str = ""
    waybill: Waybill = None
    trajectory: Trajectory = None
    temperature: TemperatureLog = None
    receipt: Receipt = None
    folder_name: str = ""

    @property
    def waybill_id_or_folder(self) -> str:
        if self.waybill:
            return self.waybill.waybill_id
        return self.folder_name


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_waybill(folder: str) -> LoadResult:
    folder_name = os.path.basename(folder)
    result = LoadResult(success=False, folder_name=folder_name)

    try:
        waybill_path = os.path.join(folder, "waybill.json")
        if not os.path.isfile(waybill_path):
            result.error_message = "缺少 waybill.json 文件"
            return result
        data = _load_json(waybill_path)

        vp = data["vaccination_point"]
        vaccination_point = VaccinationPoint(
            name=vp["name"],
            latitude=vp["latitude"],
            longitude=vp["longitude"],
            radius_km=vp.get("radius_km", 2.0),
        )

        boxes = []
        for b in data.get("vaccine_boxes", []):
            boxes.append(VaccineBox(box_code=b["box_code"], product=b["product"], quantity=b["quantity"]))

        waybill = Waybill(
            waybill_id=data["waybill_id"],
            vehicle_plate=data["vehicle_plate"],
            route=data["route"],
            carrier=data["carrier"],
            departure_time=_parse_dt(data["departure_time"]),
            outbound_order_time=_parse_dt(data["outbound_order_time"]),
            vaccination_point=vaccination_point,
            vaccine_boxes=boxes,
        )
        result.waybill = waybill
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        result.error_message = f"waybill.json 解析失败：{e}"
        return result
    except Exception as e:
        result.error_message = f"waybill.json 加载失败：{e}"
        return result

    try:
        traj_path = os.path.join(folder, "trajectory.json")
        if not os.path.isfile(traj_path):
            result.error_message = "缺少 trajectory.json 文件"
            return result
        tdata = _load_json(traj_path)
        points = [
            TrajectoryPoint(timestamp=_parse_dt(p["timestamp"]), latitude=p["latitude"], longitude=p["longitude"], speed=p.get("speed", 0))
            for p in tdata.get("points", [])
        ]
        trajectory = Trajectory(waybill_id=tdata.get("waybill_id", result.waybill.waybill_id), points=points)
        result.trajectory = trajectory
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        result.error_message = f"trajectory.json 解析失败：{e}"
        return result
    except Exception as e:
        result.error_message = f"trajectory.json 加载失败：{e}"
        return result

    try:
        temp_path = os.path.join(folder, "temperature.json")
        if not os.path.isfile(temp_path):
            result.error_message = "缺少 temperature.json 文件"
            return result
        tmpdata = _load_json(temp_path)
        records = [
            TemperatureRecord(timestamp=_parse_dt(r["timestamp"]), temperature=r["temperature"])
            for r in tmpdata.get("records", [])
        ]
        rng = tmpdata.get("range", {"min": 2.0, "max": 8.0})
        temperature = TemperatureLog(
            waybill_id=tmpdata.get("waybill_id", result.waybill.waybill_id),
            interval_minutes=tmpdata.get("interval_minutes", 5),
            records=records,
            range_min=rng.get("min", 2.0),
            range_max=rng.get("max", 8.0),
        )
        result.temperature = temperature
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        result.error_message = f"temperature.json 解析失败：{e}"
        return result
    except Exception as e:
        result.error_message = f"temperature.json 加载失败：{e}"
        return result

    try:
        rcpt_path = os.path.join(folder, "receipt.json")
        if not os.path.isfile(rcpt_path):
            result.error_message = "缺少 receipt.json 文件"
            return result
        rdata = _load_json(rcpt_path)
        box_checks = [
            BoxCheck(box_code=bc["box_code"], checked=bc.get("checked", False), photo=bc.get("photo"))
            for bc in rdata.get("box_checks", [])
        ]
        receipt = Receipt(
            waybill_id=rdata.get("waybill_id", result.waybill.waybill_id),
            recipient=rdata["recipient"],
            received_at=_parse_dt(rdata["received_at"]),
            signed=rdata.get("signed", False),
            signature_photo=rdata.get("signature_photo"),
            box_checks=box_checks,
            anomaly_note=rdata.get("anomaly_note"),
        )
        result.receipt = receipt
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        result.error_message = f"receipt.json 解析失败：{e}"
        return result
    except Exception as e:
        result.error_message = f"receipt.json 加载失败：{e}"
        return result

    result.success = True
    return result
