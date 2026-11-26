def mask_patient_name(value):
    name = str(value or "").strip()
    if not name:
        return "••••••"
    return f"{name[:2]}••••"
