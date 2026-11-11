import html
import json
import math
from pathlib import Path


MAP_COLORS = ("#d5ebe7", "#a8d7ce", "#70bdb0", "#35998d", "#087467")


def location_key(value):
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    key = " ".join(str(value).strip().casefold().replace(".", "").split())
    return key


def load_map_features(map_file):
    with Path(map_file).open(encoding="utf-8") as geojson_file:
        return json.load(geojson_file)["features"]


def map_rings(geometry):
    if geometry["type"] == "Polygon":
        return geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        return [ring for polygon in geometry["coordinates"] for ring in polygon]
    raise ValueError(f"Unsupported map geometry: {geometry['type']}")


def render_choropleth_svg(
    counts, features, key_function, aria_label, dark_mode=False
):
    coordinates = [
        point
        for feature in features
        for ring in map_rings(feature["geometry"])
        for point in ring
    ]
    if not coordinates:
        raise ValueError("The map has no boundary coordinates.")

    mean_latitude = sum(point[1] for point in coordinates) / len(coordinates)
    longitude_scale = math.cos(math.radians(mean_latitude))
    projected = [
        (longitude * longitude_scale, latitude) for longitude, latitude in coordinates
    ]
    min_x = min(point[0] for point in projected)
    max_x = max(point[0] for point in projected)
    min_y = min(point[1] for point in projected)
    max_y = max(point[1] for point in projected)

    width, height, padding = 640, 460, 18
    scale = min(
        (width - 2 * padding) / (max_x - min_x),
        (height - 2 * padding) / (max_y - min_y),
    )
    map_width = (max_x - min_x) * scale
    map_height = (max_y - min_y) * scale
    offset_x = (width - map_width) / 2
    offset_y = (height - map_height) / 2
    max_count = max(counts.values(), default=0)

    paths = []
    for feature in features:
        name = feature["properties"]["name"]
        count = counts.get(key_function(name), 0)
        if count == 0 or max_count == 0:
            color = "#273835" if dark_mode else "#edf2f1"
        else:
            color_index = min(
                len(MAP_COLORS) - 1,
                int(count / max_count * len(MAP_COLORS)),
            )
            color = MAP_COLORS[color_index]

        path_data = []
        for ring in map_rings(feature["geometry"]):
            points = []
            for longitude, latitude in ring:
                x = (longitude * longitude_scale - min_x) * scale + offset_x
                y = height - ((latitude - min_y) * scale + offset_y)
                points.append(f"{x:.1f},{y:.1f}")
            if points:
                path_data.append("M" + " L".join(points) + " Z")

        paths.append(
            f'<path d="{" ".join(path_data)}" fill="{color}" '
            f'stroke="{"#344945" if dark_mode else "#ffffff"}" '
            f'stroke-width="1.5" fill-rule="evenodd">'
            f"<title>{html.escape(name)}: {count} patient records</title></path>"
        )

    legend = "".join(
        f'<span style="display:inline-block;width:22px;height:12px;'
        f'background:{color};border:1px solid #c8d3d1"></span>'
        for color in MAP_COLORS
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{html.escape(aria_label)}" '
        f'style="display:block;width:100%;height:auto;'
        f'background:{"#182523" if dark_mode else "transparent"}">'
        f'{"".join(paths)}</svg>'
        f'<div style="display:flex;align-items:center;justify-content:center;'
        f'gap:6px;font:12px sans-serif;'
        f'color:{"#e5efed" if dark_mode else "#465452"};margin-top:8px">'
        f'<span>No records</span><span style="display:inline-block;width:18px;'
        f'height:12px;background:{"#273835" if dark_mode else "#edf2f1"};'
        f'border:1px solid {"#52645f" if dark_mode else "#c8d3d1"}"></span>'
        f'<span>Fewer</span>{legend}<span>More</span></div>'
    )
