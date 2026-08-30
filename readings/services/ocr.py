import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path


logger = logging.getLogger(__name__)
NUMBER_PATTERN = re.compile(r"^\s*(\d{3,10}(?:[.,]\d{1,3})?)\s*$")


@dataclass(frozen=True)
class OCRResult:
    value: Decimal | None
    raw_text: str
    confidence: float | None
    source: str = "local"


@dataclass(frozen=True)
class OCRCandidate:
    value: Decimal
    confidence: float
    method: str
    variant: str


@dataclass
class DisplayRegion:
    image: object
    score: float
    label: str


def _parse_value(text):
    match = NUMBER_PATTERN.match(str(text))
    if not match:
        return None
    try:
        return Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None


def select_meter_value(result) -> OCRResult:
    """Compatibilidad: selecciona el número más grande de un resultado OCR completo."""
    if not result:
        return OCRResult(value=None, raw_text="", confidence=None)
    candidates = []
    raw_parts = []
    for box, text, confidence in result:
        raw_parts.append(str(text))
        value = _parse_value(text)
        if value is None:
            continue
        height = max(point[1] for point in box) - min(point[1] for point in box)
        width = max(point[0] for point in box) - min(point[0] for point in box)
        score = (height * 3) + width + (float(confidence) * 100)
        candidates.append((score, value, float(confidence)))
    raw_text = " | ".join(raw_parts)
    if not candidates:
        return OCRResult(value=None, raw_text=raw_text, confidence=None)
    _, value, confidence = max(candidates, key=lambda item: item[0])
    return OCRResult(value=value, raw_text=raw_text, confidence=confidence)


def find_display_crop(image, result, width_factor=11.75):
    """Usa kWh como una pista adicional, pero ya no es el único localizador."""
    if image is None or not result:
        return None
    anchors = []
    for box, text, _confidence in result:
        normalized = re.sub(r"[^a-z]", "", str(text).lower())
        if normalized != "kwh":
            continue
        x_min = min(point[0] for point in box)
        x_max = max(point[0] for point in box)
        y_min = min(point[1] for point in box)
        y_max = max(point[1] for point in box)
        anchors.append((y_min, x_min, x_max, y_max))
    if not anchors:
        return None
    y_min, x_min, _x_max, y_max = min(anchors)
    anchor_height = max(8, y_max - y_min)
    image_height, image_width = image.shape[:2]
    left = max(0, int(x_min - (width_factor * anchor_height)))
    right = min(image_width, int(x_min + (0.25 * anchor_height)))
    top = max(0, int(y_min - (1.4 * anchor_height)))
    bottom = min(image_height, int(y_max + (1.35 * anchor_height)))
    if right - left < 40 or bottom - top < 20:
        return None
    return image[top:bottom, left:right]


def find_kba_display_crop(image, result):
    """Usa KBA como pista adicional para los visores tenues de ese fabricante."""
    if image is None or not result:
        return None
    anchors = []
    for box, text, _confidence in result:
        normalized = re.sub(r"[^a-z]", "", str(text).lower())
        if normalized != "kba":
            continue
        x_min = min(point[0] for point in box)
        x_max = max(point[0] for point in box)
        y_min = min(point[1] for point in box)
        y_max = max(point[1] for point in box)
        anchors.append((y_min, x_min, x_max, y_max))
    if not anchors:
        return None
    y_min, x_min, x_max, y_max = min(anchors)
    anchor_width = max(20, x_max - x_min)
    anchor_height = max(12, y_max - y_min)
    image_height, image_width = image.shape[:2]
    left = max(0, int(x_min + (0.02 * anchor_width)))
    right = min(image_width, int(x_max + (1.80 * anchor_width)))
    top = max(0, int(y_min - (4.15 * anchor_height)))
    bottom = min(image_height, int(y_min - (2.20 * anchor_height)))
    if right - left < 80 or bottom - top < 30:
        return None
    return image[top:bottom, left:right]


def _order_points(points):
    import numpy as np

    points = np.asarray(points, dtype="float32").reshape(4, 2)
    ordered = np.zeros((4, 2), dtype="float32")
    sums = points.sum(axis=1)
    differences = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[sums.argmin()]
    ordered[2] = points[sums.argmax()]
    ordered[1] = points[differences.argmin()]
    ordered[3] = points[differences.argmax()]
    return ordered


def _perspective_crop(image, points):
    import cv2
    import numpy as np

    top_left, top_right, bottom_right, bottom_left = _order_points(points)
    width = int(max(np.linalg.norm(bottom_right - bottom_left), np.linalg.norm(top_right - top_left)))
    height = int(max(np.linalg.norm(top_right - bottom_right), np.linalg.norm(top_left - bottom_left)))
    if width < 80 or height < 20:
        return None
    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32"
    )
    matrix = cv2.getPerspectiveTransform(_order_points(points), destination)
    return cv2.warpPerspective(image, matrix, (width, height))


def _intersection_over_union(first, second):
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    first_area = max(1, (first[2] - first[0]) * (first[3] - first[1]))
    second_area = max(1, (second[2] - second[0]) * (second[3] - second[1]))
    return intersection / float(first_area + second_area - intersection)


def find_display_regions(image, full_ocr=None, limit=6):
    """Localiza visores rectangulares por contorno y rectifica su perspectiva."""
    import cv2
    import numpy as np

    if image is None or image.size == 0:
        return []
    height, width = image.shape[:2]
    image_area = float(height * width)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.bilateralFilter(clahe, 7, 45, 45)
    detection_images = [
        cv2.Canny(blurred, 35, 120),
        cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 8
        ),
    ]
    found = []
    boxes = []
    for detected in detection_images:
        closed = cv2.morphologyEx(
            detected, cv2.MORPH_CLOSE, np.ones((5, 9), np.uint8), iterations=2
        )
        contours, _ = cv2.findContours(closed, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            polygon = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
            x, y, box_width, box_height = cv2.boundingRect(polygon)
            area = float(cv2.contourArea(polygon))
            if box_width < 100 or box_height < 24 or not (0.002 <= area / image_area <= 0.45):
                continue
            aspect = box_width / float(max(1, box_height))
            if not 2.0 <= aspect <= 10.5:
                continue
            box = (x, y, x + box_width, y + box_height)
            if any(_intersection_over_union(box, existing) > 0.72 for existing in boxes):
                continue
            if len(polygon) == 4 and cv2.isContourConvex(polygon):
                crop = _perspective_crop(image, polygon)
                label = "contorno-perspectiva"
            else:
                # Algunos marcos LCD tienen esquinas redondeadas o reflejos que generan
                # más de cuatro vértices. Su rectángulo envolvente sigue siendo una pista útil.
                padding_x = max(2, int(box_width * 0.015))
                padding_y = max(2, int(box_height * 0.04))
                left = max(0, x - padding_x)
                top = max(0, y - padding_y)
                right = min(width, x + box_width + padding_x)
                bottom = min(height, y + box_height + padding_y)
                crop = image[top:bottom, left:right]
                label = "contorno-rectangular"
            if crop is None:
                continue
            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            texture = min(1.0, float(crop_gray.std()) / 55.0)
            rectangularity = min(1.0, area / float(box_width * box_height))
            aspect_score = max(0.0, 1.0 - abs(aspect - 4.8) / 6.0)
            center_x = (x + box_width / 2) / width
            center_score = max(0.0, 1.0 - abs(center_x - 0.5))
            score = rectangularity + aspect_score + texture + (0.35 * center_score)
            boxes.append(box)
            found.append(DisplayRegion(crop, score, label))
    for label, crop in (
        ("ancla-kWh", find_display_crop(image, full_ocr, width_factor=11.75)),
        ("ancla-KBA", find_kba_display_crop(image, full_ocr)),
    ):
        if crop is not None and crop.size:
            found.append(DisplayRegion(crop, 3.6, label))

    # Si RapidOCR vio una secuencia numérica grande, su caja delimita los
    # dígitos del visor. Se vuelve a reconocer solo esa zona; el texto completo
    # jamás se acepta directamente, evitando series y fechas impresas.
    numeric_boxes = []
    for box, text, confidence in full_ocr or []:
        if _parse_value(text) is None or float(confidence) < 0.55:
            continue
        x_min = int(min(point[0] for point in box))
        x_max = int(max(point[0] for point in box))
        y_min = int(min(point[1] for point in box))
        y_max = int(max(point[1] for point in box))
        numeric_boxes.append((y_max - y_min, x_min, y_min, x_max, y_max))
    maximum_numeric_height = max((item[0] for item in numeric_boxes), default=0)
    for box_height, x_min, y_min, x_max, y_max in numeric_boxes:
        box_width = x_max - x_min
        if box_height < maximum_numeric_height * 0.72 or box_width < 70:
            continue
        padding_x = max(5, int(box_height * 0.45))
        padding_y = max(4, int(box_height * 0.35))
        left = max(0, x_min - padding_x)
        right = min(width, x_max + padding_x)
        top = max(0, y_min - padding_y)
        bottom = min(height, y_max + padding_y)
        crop = image[top:bottom, left:right]
        if crop.size:
            found.append(DisplayRegion(crop, 3.9, "caja-numerica-del-visor"))
    found.sort(key=lambda region: region.score, reverse=True)
    return found[:limit]


def generate_display_variants(display):
    """Genera variantes para LCD tenue, reflejos, segmentos claros y oscuros."""
    import cv2
    import numpy as np

    if display is None or display.size == 0:
        return []
    scale = max(2.0, min(5.0, 900.0 / max(1, display.shape[1])))
    enlarged = cv2.resize(display, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.2, tileGridSize=(8, 8)).apply(gray)
    hsv = cv2.cvtColor(enlarged, cv2.COLOR_BGR2HSV)
    reflection_mask = cv2.inRange(hsv, (0, 0, 205), (179, 70, 255))
    reflection_mask = cv2.morphologyEx(
        reflection_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)
    )
    reduced = cv2.inpaint(enlarged, reflection_mask, 3, cv2.INPAINT_TELEA)
    reduced_gray = cv2.cvtColor(reduced, cv2.COLOR_BGR2GRAY)
    reduced_gray = cv2.createCLAHE(clipLimit=2.8, tileGridSize=(8, 8)).apply(reduced_gray)
    adaptive = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 7
    )
    _level, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return [
        ("gris", gray),
        ("clahe", clahe),
        ("sin-reflejo", reduced_gray),
        ("adaptativo", adaptive),
        ("adaptativo-invertido", cv2.bitwise_not(adaptive)),
        ("otsu", otsu),
        ("otsu-invertido", cv2.bitwise_not(otsu)),
    ]


def select_direct_recognition(result, raw_text="") -> OCRResult:
    """Interpreta el reconocedor aplicado directamente al interior del visor."""
    if not result:
        return OCRResult(value=None, raw_text=raw_text, confidence=None)
    candidates = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text, confidence = str(item[0]), float(item[1])
        value = _parse_value(text)
        if value is None or confidence < 0.60:
            continue
        digit_count = sum(character.isdigit() for character in text)
        has_decimal = "." in text or "," in text
        candidates.append((digit_count, has_decimal, confidence, value, text))
    if not candidates:
        return OCRResult(value=None, raw_text=raw_text, confidence=None)
    _digit_count, _has_decimal, confidence, value, text = max(
        candidates, key=lambda item: (item[0], item[1], item[2])
    )
    combined_text = f"{raw_text} | VISOR: {text}" if raw_text else f"VISOR: {text}"
    return OCRResult(value=value, raw_text=combined_text, confidence=confidence)


SEGMENT_DIGITS = {
    (1, 1, 1, 0, 1, 1, 1): "0",
    (0, 0, 1, 0, 0, 1, 0): "1",
    (1, 0, 1, 1, 1, 0, 1): "2",
    (1, 0, 1, 1, 0, 1, 1): "3",
    (0, 1, 1, 1, 0, 1, 0): "4",
    (1, 1, 0, 1, 0, 1, 1): "5",
    (1, 1, 0, 1, 1, 1, 1): "6",
    (1, 0, 1, 0, 0, 1, 0): "7",
    (1, 1, 1, 1, 1, 1, 1): "8",
    (1, 1, 1, 1, 0, 1, 1): "9",
}


def _segment_state(cell):
    import cv2

    height, width = cell.shape[:2]
    if height < 20 or width < 8:
        return None
    thickness_x = max(1, int(width * 0.16))
    thickness_y = max(1, int(height * 0.10))
    segments = [
        cell[0:2 * thickness_y, int(width * .22):int(width * .78)],
        cell[int(height * .12):int(height * .46), 0:2 * thickness_x],
        cell[int(height * .12):int(height * .46), width - 2 * thickness_x:width],
        cell[int(height * .43):int(height * .57), int(width * .22):int(width * .78)],
        cell[int(height * .54):int(height * .88), 0:2 * thickness_x],
        cell[int(height * .54):int(height * .88), width - 2 * thickness_x:width],
        cell[height - 2 * thickness_y:height, int(width * .22):int(width * .78)],
    ]
    ratios = [cv2.countNonZero(part) / float(max(1, part.size)) for part in segments]
    state = tuple(1 if ratio >= 0.28 else 0 for ratio in ratios)
    best_state, digit = min(
        SEGMENT_DIGITS.items(),
        key=lambda item: sum(a != b for a, b in zip(state, item[0])),
    )
    distance = sum(a != b for a, b in zip(state, best_state))
    if distance > 1:
        return None
    return digit, 1.0 - (distance / 7.0)


def recognize_seven_segment(binary):
    """Reconocedor geométrico específico para pantallas LCD de siete segmentos."""
    import cv2

    if binary is None or binary.size == 0:
        return None
    if len(binary.shape) == 3:
        binary = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)
    _level, mask = cv2.threshold(binary, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if cv2.countNonZero(mask) > mask.size * 0.55:
        mask = cv2.bitwise_not(mask)
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, width, height = cv2.boundingRect(points)
    if width < 60 or height < 20:
        return None
    mask = mask[y:y + height, x:x + width]
    possibilities = []
    for count in range(4, 11):
        cell_width = mask.shape[1] / float(count)
        if not 0.28 <= cell_width / mask.shape[0] <= 1.05:
            continue
        digits = []
        confidences = []
        valid = True
        for index in range(count):
            left = int(index * cell_width)
            right = int((index + 1) * cell_width)
            decoded = _segment_state(mask[:, left:right])
            if decoded is None:
                valid = False
                break
            digit, confidence = decoded
            digits.append(digit)
            confidences.append(confidence)
        if valid:
            possibilities.append((sum(confidences) / len(confidences), "".join(digits)))
    if not possibilities:
        return None
    confidence, text = max(possibilities, key=lambda item: (item[0], len(item[1])))
    if confidence < 0.80:
        return None
    return OCRCandidate(Decimal(text), confidence, "siete-segmentos", "binaria")


def detect_red_decimal(image, result, base_result, engine) -> OCRResult | None:
    """Lee la rueda roja de décimas ubicada al final de algunos medidores mecánicos."""
    if image is None or not result or base_result.value is None:
        return None
    if base_result.value.as_tuple().exponent < 0:
        return None
    base_text = format(base_result.value, "f")
    numeric_items = []
    for box, text, _confidence in result:
        if str(text).strip() != base_text:
            continue
        height = max(point[1] for point in box) - min(point[1] for point in box)
        width = max(point[0] for point in box) - min(point[0] for point in box)
        numeric_items.append((height * width, box))
    if not numeric_items:
        return None
    import cv2

    _area, box = max(numeric_items, key=lambda item: item[0])
    x_max = max(point[0] for point in box)
    y_min = min(point[1] for point in box)
    y_max = max(point[1] for point in box)
    height = max(12, y_max - y_min)
    image_height, image_width = image.shape[:2]
    left = max(0, int(x_max - (0.33 * height)))
    right = min(image_width, int(x_max + (0.44 * height)))
    top = max(0, int(y_min - (0.21 * height)))
    bottom = min(image_height, int(y_max + (0.20 * height)))
    crop = image[top:bottom, left:right]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    red_mask = cv2.inRange(hsv, (0, 40, 20), (15, 255, 255))
    red_mask |= cv2.inRange(hsv, (165, 40, 20), (179, 255, 255))
    red_ratio = float(cv2.countNonZero(red_mask)) / float(red_mask.size)
    if red_ratio < 0.025:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    recognized, _ = engine(gray, use_det=False, use_cls=False)
    digit_candidates = []
    for item in recognized or []:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text, confidence = str(item[0]).strip(), float(item[1])
        if re.fullmatch(r"\d", text) and confidence >= 0.35:
            digit_candidates.append((confidence, text))
    if not digit_candidates:
        return None
    digit_confidence, digit = max(digit_candidates)
    value = Decimal(f"{base_text}.{digit}")
    raw_text = f"{base_result.raw_text} | DÍGITO ROJO: {digit}"
    confidence = min(base_result.confidence or digit_confidence, digit_confidence)
    return OCRResult(value=value, raw_text=raw_text, confidence=confidence)


@lru_cache(maxsize=1)
def _rapid_ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _rapid_candidates(engine, region, region_index):
    candidates = []
    for variant_name, variant in generate_display_variants(region.image):
        recognized, _ = engine(variant, use_det=False, use_cls=False)
        for item in recognized or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            value = _parse_value(item[0])
            confidence = float(item[1])
            if value is not None and confidence >= 0.58:
                candidates.append(
                    OCRCandidate(value, confidence, "rapidocr", f"visor-{region_index}:{variant_name}")
                )
        if (
            region.label in {"caja-numerica-del-visor", "ancla-kWh", "ancla-KBA"}
            and variant_name == "gris"
        ):
            detected, _ = engine(variant)
            for _box, text, confidence in detected or []:
                value = _parse_value(text)
                confidence = float(confidence)
                if value is not None and confidence >= 0.58:
                    candidates.append(
                        OCRCandidate(
                            value,
                            confidence,
                            "rapidocr-deteccion",
                            f"visor-{region_index}:{variant_name}-detectado",
                        )
                    )
        if "adaptativo" in variant_name or "otsu" in variant_name:
            seven_segment = recognize_seven_segment(variant)
            if seven_segment is not None:
                candidates.append(
                    OCRCandidate(
                        seven_segment.value,
                        seven_segment.confidence,
                        seven_segment.method,
                        f"visor-{region_index}:{variant_name}",
                    )
                )
    return candidates


def choose_consistent_candidate(candidates, previous_value=None):
    """Exige repetición entre variantes y descarta valores no superiores al anterior."""
    grouped = defaultdict(list)
    for candidate in candidates:
        # Agrupa 157519.2 y 1575192 como la misma secuencia visual. Algunos
        # preprocesamientos borran el punto del LCD; si otra variante sí lo ve,
        # se conserva la representación decimal.
        digits = "".join(str(digit) for digit in candidate.value.as_tuple().digits).lstrip("0") or "0"
        grouped[digits].append(candidate)
    ranked = []
    for digits, items in grouped.items():
        variants = {item.variant for item in items}
        methods = {item.method for item in items}
        maximum = max(item.confidence for item in items)
        average = sum(item.confidence for item in items) / len(items)
        # El lector geométrico de siete segmentos confirma RapidOCR, pero no se
        # acepta por sí solo porque marcos y reflejos pueden parecer segmentos.
        if (
            len(variants) < 2
            or maximum < 0.68
            or average < 0.62
            or "rapidocr" not in methods
        ):
            continue
        decimal_items = [
            item for item in items
            if item.value.as_tuple().exponent < 0 and item.confidence >= 0.82
        ]
        representations = defaultdict(list)
        for item in decimal_items or items:
            representations[item.value].append(item)
        value, representation_items = max(
            representations.items(),
            key=lambda pair: (len(pair[1]), max(item.confidence for item in pair[1])),
        )
        if previous_value is not None and value <= Decimal(previous_value):
            continue
        # Una lectura completa de 6 o 7 dígitos es preferible a un fragmento
        # repetido muchas veces dentro de un recorte parcial.
        score = (len(digits) * 1.25) + min(len(variants), 4) + (len(methods) * 0.5) + average
        ranked.append((score, value, average, len(variants), methods))
    if not ranked:
        return OCRResult(None, "LOCAL: sin consenso suficiente", None)
    ranked.sort(reverse=True, key=lambda item: item[0])
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.35:
        return OCRResult(None, "LOCAL: resultados ambiguos entre variantes", None)
    _score, value, confidence, votes, methods = ranked[0]
    raw = f"LOCAL: {value} confirmado por {votes} variantes ({', '.join(sorted(methods))})"
    return OCRResult(value, raw, confidence, "local")


def read_meter_local(image_path: str | Path, previous_value=None):
    """Ejecuta únicamente el reconocimiento local sobre el interior de los visores."""
    import cv2

    image = cv2.imread(str(image_path))
    if image is None:
        return OCRResult(None, "LOCAL: no se pudo abrir la imagen", None), [], None
    engine = _rapid_ocr_engine()
    full_result, _ = engine(image)
    regions = find_display_regions(image, full_result)
    candidates = []
    for index, region in enumerate(regions):
        candidates.extend(_rapid_candidates(engine, region, index))
    numeric_detections = []
    for index, item in enumerate(full_result or []):
        box, text, confidence = item
        value = _parse_value(text)
        if value is None:
            continue
        box_height = max(point[1] for point in box) - min(point[1] for point in box)
        box_width = max(point[0] for point in box) - min(point[0] for point in box)
        numeric_detections.append((box_height, box_width, index, value, float(confidence)))
    maximum_height = max((item[0] for item in numeric_detections), default=0)
    for box_height, box_width, index, value, confidence in numeric_detections:
        if box_height >= maximum_height * 0.72 and box_width >= 70 and confidence >= 0.58:
            candidates.append(
                OCRCandidate(
                    value,
                    confidence,
                    "rapidocr-deteccion",
                    f"visor-detectado-original-{index}",
                )
            )
    local = choose_consistent_candidate(candidates, previous_value)
    full_selection = select_meter_value(full_result)
    mechanical = detect_red_decimal(image, full_result, full_selection, engine)
    if mechanical is not None and (
        previous_value is None or mechanical.value > Decimal(previous_value)
    ):
        if local.value is None or (mechanical.confidence or 0) > (local.confidence or 0):
            local = mechanical
    return local, regions, image


def _extract_json_object(value):
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    try:
        return json.loads(fenced)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", fenced, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def read_meter_cloudflare(image, previous_value=None):
    """Consulta Workers AI solo cuando están configuradas sus credenciales."""
    import cv2

    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
    model = os.getenv(
        "CLOUDFLARE_VISION_MODEL", "@cf/moondream/moondream3.1-9B-A2B"
    ).strip()
    if not account_id or not api_token:
        return OCRResult(None, "CLOUDFLARE: no configurado", None, "manual")
    if image is None or image.size == 0:
        return OCRResult(None, "CLOUDFLARE: no hay visor para analizar", None, "manual")
    max_dimension = max(image.shape[:2])
    if max_dimension > 1600:
        scale = 1600.0 / max_dimension
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    encoded_ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 92])
    if not encoded_ok:
        return OCRResult(None, "CLOUDFLARE: no se pudo preparar el visor", None, "manual")
    data_url = "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode("ascii")
    previous_instruction = (
        f" La lectura anterior confirmada es {previous_value}; el resultado debe ser estrictamente mayor."
        if previous_value is not None
        else ""
    )
    prompt = (
        "Observa exclusivamente los dígitos dentro del visor del medidor eléctrico. "
        "Ignora marcas, números de serie, fechas, coordenadas y etiquetas impresas. "
        "Conserva el punto decimal visible. Si no puedes leerlo con seguridad, devuelve reading null."
        f"{previous_instruction} Devuelve únicamente JSON."
    )
    is_moondream = "moondream" in model.lower()
    if is_moondream:
        payload = {
            "task": "query",
            "image": data_url,
            "question": (
                "Read only the large numeric electricity meter reading inside the LCD display. "
                "Ignore voltage, serial numbers, dates, coordinates, labels and all printed text. "
                "Preserve the visible decimal point. Reply with only the reading number, or UNKNOWN "
                f"if it is not legible.{previous_instruction}"
            ),
            "reasoning": False,
            "stream": False,
            "temperature": 0,
            "max_tokens": 40,
        }
    else:
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "Eres un lector preciso de visores LCD de medidores eléctricos.",
                },
                {"role": "user", "content": prompt},
            ],
            "image": data_url,
            "temperature": 0,
            "max_tokens": 100,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "reading": {"type": ["string", "null"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["reading", "confidence"],
                },
            },
        }
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        timeout = max(5, min(60, int(os.getenv("CLOUDFLARE_TIMEOUT_SECONDS", "25"))))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            envelope = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as error:
        logger.warning("Falló el OCR de Cloudflare: %s", error)
        return OCRResult(None, "CLOUDFLARE: servicio no disponible", None, "manual")
    if not envelope.get("success", False):
        return OCRResult(None, "CLOUDFLARE: respuesta rechazada", None, "manual")
    result = envelope.get("result", {})
    if is_moondream:
        nested = result.get("result", result) if isinstance(result, dict) else {}
        answer = nested.get("answer") if isinstance(nested, dict) else None
        value = _parse_value(answer)
        if value is None:
            return OCRResult(None, "CLOUDFLARE: lectura insegura", None, "manual")
        if previous_value is not None and value <= Decimal(previous_value):
            return OCRResult(
                None, f"CLOUDFLARE: lectura {value} no supera la anterior", None, "manual"
            )
        return OCRResult(
            value, f"CLOUDFLARE: visor reconocido como {value}", 0.90, "cloudflare"
        )
    parsed = _extract_json_object(
        result.get("response", result) if isinstance(result, dict) else result
    )
    if not parsed:
        return OCRResult(None, "CLOUDFLARE: respuesta sin lectura válida", None, "manual")
    value = _parse_value(parsed.get("reading"))
    try:
        confidence = float(parsed.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0
    if value is None or confidence < 0.72:
        return OCRResult(None, "CLOUDFLARE: lectura insegura", None, "manual")
    if previous_value is not None and value <= Decimal(previous_value):
        return OCRResult(
            None, f"CLOUDFLARE: lectura {value} no supera la anterior", None, "manual"
        )
    return OCRResult(
        value, f"CLOUDFLARE: visor reconocido como {value}", confidence, "cloudflare"
    )


def read_meter(image_path: str | Path, previous_value=None) -> OCRResult:
    """OCR local primero; Cloudflare solo actúa como respaldo y luego queda el modo manual."""
    local, regions, image = read_meter_local(image_path, previous_value)
    if local.value is not None:
        return local
    # Solo se usa un recorte cuando la caja numérica identifica el visor con
    # precisión. Las anclas kWh pueden quedar debajo del LCD; en ese caso el
    # modelo visual recibe la foto completa para localizarlo correctamente.
    precise_region = next(
        (region for region in regions if region.label == "caja-numerica-del-visor"),
        None,
    )
    external_image = precise_region.image if precise_region is not None else image
    cloudflare = read_meter_cloudflare(external_image, previous_value)
    if cloudflare.value is not None:
        return cloudflare
    return OCRResult(
        None,
        f"{local.raw_text} | {cloudflare.raw_text} | REQUIERE INGRESO MANUAL",
        None,
        "manual",
    )
