#!/usr/bin/env python3
"""Create templ_mag_area.log from existing complex-fault rupture XML files.

Run from the FinDer_TemplGen/make_fault_specific directory, or provide
--xml-dir and --output explicitly. This script does not run OpenQuake and
does not create PNG files or overwrite rupture XML files.

The reconstructed length and width are geometric estimates from the XML:
- length: the larger cumulative geodesic length of the top and bottom edges;
- width: the larger of the two endpoint separations between those edges;
- area: length * width.

out2templ.py uses length, width, magnitude, and lat/lon bounds. It does not
use the area field when making templates, but area is included for compatibility
with the historical log format.
"""

from __future__ import annotations

import argparse
import math
import os
import xml.etree.ElementTree as ET
from pathlib import Path

from pyproj import Geod


GEOD = Geod(ellps="WGS84")
HEADER = "Mag, area, len, wid, lat/lon"


def local_name(tag: str) -> str:
    """Return an XML tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def read_edge_points(edge_element: ET.Element) -> list[tuple[float, float, float]]:
    """Read lon, lat, depth triples from an XML fault edge."""
    pos_list = edge_element.find(".//{*}posList")
    if pos_list is None or not pos_list.text:
        raise ValueError("fault edge has no gml:posList")

    values = [float(value) for value in pos_list.text.split()]
    if len(values) % 3:
        raise ValueError("posList does not contain lon/lat/depth triples")

    return [tuple(values[i:i + 3]) for i in range(0, len(values), 3)]


def line_length_km(points: list[tuple[float, float, float]]) -> float:
    """Calculate cumulative horizontal geodesic length in km."""
    total_m = 0.0
    for p1, p2 in zip(points, points[1:]):
        _, _, distance_m = GEOD.inv(p1[0], p1[1], p2[0], p2[1])
        total_m += abs(distance_m)
    return total_m / 1000.0


def endpoint_widths_km(
    top: list[tuple[float, float, float]],
    bottom: list[tuple[float, float, float]],
) -> list[float]:
    """Estimate width at the two rupture ends."""
    widths = []
    for p1, p2 in ((top[0], bottom[0]), (top[-1], bottom[-1])):
        _, _, distance_m = GEOD.inv(p1[0], p1[1], p2[0], p2[1])
        depth_difference_m = abs(p1[2] - p2[2]) * 1000.0
        widths.append(math.hypot(distance_m, depth_difference_m) / 1000.0)
    return widths


def parse_rupture(xml_path: Path) -> tuple[float, float, float, float, float, float, float, float]:
    """Return magnitude, area, length, width, minlat, maxlat, minlon, maxlon."""
    root = ET.parse(xml_path).getroot()

    magnitude_element = next(
        (element for element in root.iter() if local_name(element.tag) == "magnitude"),
        None,
    )
    if magnitude_element is None or magnitude_element.text is None:
        raise ValueError("magnitude element is missing")
    magnitude = float(magnitude_element.text.strip())

    edges = {
        local_name(element.tag): element
        for element in root.iter()
        if local_name(element.tag) in {"faultTopEdge", "faultBottomEdge"}
    }
    if "faultTopEdge" not in edges or "faultBottomEdge" not in edges:
        raise ValueError("faultTopEdge or faultBottomEdge is missing")

    top = read_edge_points(edges["faultTopEdge"])
    bottom = read_edge_points(edges["faultBottomEdge"])
    all_points = top + bottom

    length_km = max(line_length_km(top), line_length_km(bottom))
    width_values_km = endpoint_widths_km(top, bottom)
    width_km = max(width_values_km)
    area_km2 = length_km * width_km

    lons = [point[0] for point in all_points]
    lats = [point[1] for point in all_points]
    return (
        magnitude,
        area_km2,
        length_km,
        width_km,
        min(lats),
        max(lats),
        min(lons),
        max(lons),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml-dir", default="event_xmls", type=Path)
    parser.add_argument("--output", default="templ_mag_area.log", type=Path)
    args = parser.parse_args()

    xml_files = sorted(args.xml_dir.glob("*.xml"))
    if not xml_files:
        parser.error(f"no XML files found in {args.xml_dir}")

    written = 0
    failed = 0
    with args.output.open("w", encoding="utf-8") as output:
        output.write(HEADER + "\n")
        for xml_path in xml_files:
            try:
                magnitude, area, length, width, minlat, maxlat, minlon, maxlon = parse_rupture(xml_path)
            except Exception as exc:
                failed += 1
                print(f"WARNING: skipped {xml_path}: {exc}")
                continue

            output.write(
                f"event_xmls/{xml_path.name}, "
                f"{magnitude:.1f}, "
                f"{area:.1f}, "
                f"{length:.1f}, "
                f"{width:.1f}, "
                f"{minlat:.6f};{maxlat:.6f};{minlon:.6f};{maxlon:.6f}\n"
            )
            written += 1

    print(f"Wrote {args.output} with {written} rupture records.")
    if failed:
        print(f"WARNING: {failed} XML files could not be converted.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
