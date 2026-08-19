import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass(frozen=True)
class OCRResult:
    value: Decimal | None
    raw_text: str
    confidence: float | None


def select_meter_value(result) -> OCRResult:
    """Prioriza cifras puras, grandes y confiables; ignora fechas, coordenadas y textos superpuestos."""
    if not result:
        return OCRResult(value=None, raw_text="", confidence=None)

    candidates = []
    raw_parts = []
    number_pattern = re.compile(r"^\s*(\d{3,10}(?:[.,]\d{1,3})?)\s*$")
    for box, text, confidence in result:
        raw_parts.append(text)
        match = number_pattern.match(text)
        if not match:
            continue
        normalized = match.group(1).replace(",", ".")
        try:
            value = Decimal(normalized)
        except InvalidOperation:
            continue
        height = max(point[1] for point in box) - min(point[1] for point in box)
        width = max(point[0] for point in box) - min(point[0] for point in box)
        # La lectura del display suele ser el texto numérico más alto y ancho de la imagen.
        score = (height * 3) + width + (float(confidence) * 100)
        candidates.append((score, value, float(confidence)))

    raw_text = " | ".join(raw_parts)
    if not candidates:
        return OCRResult(value=None, raw_text=raw_text, confidence=None)
    _, value, confidence = max(candidates, key=lambda item: item[0])
    return OCRResult(value=value, raw_text=raw_text, confidence=confidence)


def find_display_crop(image, result, width_factor=11.75):
    """Usa la etiqueta kWh como ancla para aislar el visor situado a su izquierda."""
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
    """Aísla el LCD tenue de los medidores KBA usando el logotipo como referencia."""
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


def select_direct_recognition(result, raw_text="") -> OCRResult:
    """Interpreta el resultado del reconocedor aplicado directamente al visor."""
    if not result:
        return OCRResult(value=None, raw_text=raw_text, confidence=None)
    pattern = re.compile(r"^\s*(\d{3,10}(?:[.,]\d{1,3})?)\s*$")
    candidates = []
    for item in result:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        text, confidence = str(item[0]), float(item[1])
        match = pattern.match(text)
        if not match or confidence < 0.60:
            continue
        try:
            value = Decimal(match.group(1).replace(",", "."))
        except InvalidOperation:
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


def read_meter(image_path: str | Path) -> OCRResult:
    """Lee dígitos de forma local. No envía la imagen a ningún servicio externo."""
    import cv2
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    image = cv2.imread(str(image_path))
    result, _ = engine(image)
    initial = select_meter_value(result)
    mechanical = detect_red_decimal(image, result, initial, engine)
    if mechanical is not None:
        return mechanical
    display_gray = find_display_crop(image, result, width_factor=14)
    display_contrast = find_display_crop(image, result, width_factor=11.75)
    if display_gray is None or display_contrast is None:
        kba_display = find_kba_display_crop(image, result)
        display_gray = display_gray if display_gray is not None else kba_display
        display_contrast = display_contrast if display_contrast is not None else kba_display
    if display_gray is None or display_contrast is None:
        return initial
    gray = cv2.cvtColor(display_gray, cv2.COLOR_BGR2GRAY)
    contrast = cv2.cvtColor(display_contrast, cv2.COLOR_BGR2GRAY)
    contrast = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(contrast)
    variants = [
        cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC),
        cv2.resize(contrast, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC),
    ]
    direct_results = []
    for variant in variants:
        recognized, _ = engine(variant, use_det=False, use_cls=False)
        direct_results.extend(recognized or [])
    improved = select_direct_recognition(direct_results, initial.raw_text)
    if improved.value is None:
        return initial
    if initial.value is None:
        return improved
    initial_digits = len(initial.value.as_tuple().digits)
    improved_digits = len(improved.value.as_tuple().digits)
    if improved_digits > initial_digits:
        return improved
    if improved_digits == initial_digits and improved.value.as_tuple().exponent < initial.value.as_tuple().exponent:
        return improved
    return initial
