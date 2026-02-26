"""
SPEC data file parser for BL15-2 beamline scan data.

Parses standard SPEC file format:
  #F, #E, #D - file metadata
  #O0..#On   - motor name definitions (8 per line, whitespace separated)
  #S n cmd   - scan header (number + command)
  #P0..#Pn   - motor positions (mapped to #O names)
  #N n       - number of data columns
  #L labels  - column labels
  (data rows follow #L)
"""

import re
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class Scan:
    """A single scan from a SPEC data file."""
    scan_number: int
    command: str
    scan_type: str
    scanned_motors: list
    date: str
    motor_positions: dict       # motor_name -> float
    column_labels: list
    num_columns: int
    data: np.ndarray            # shape (npoints, ncols)
    expected_points: Optional[int]

    @property
    def actual_points(self) -> int:
        if self.data is not None and self.data.size > 0:
            return self.data.shape[0]
        return 0

    @property
    def is_complete(self) -> bool:
        if self.expected_points is None:
            return True
        return self.actual_points >= self.expected_points


@dataclass
class SpecFile:
    """A parsed SPEC data file."""
    filepath: str
    motor_names: list           # flat list from all #O lines
    scans: dict                 # scan_number -> Scan


def parse_scan_command(command_str: str):
    """
    Parse a SPEC scan command to extract scanned motors and expected point count.

    Returns: (scanned_motors: list, expected_points: int|None, scan_type: str)
    """
    parts = command_str.split()
    if not parts:
        return [], None, ""

    scan_type = parts[0]

    try:
        if scan_type in ("ascan", "dscan", "lup"):
            # ascan motor start end npts time
            if len(parts) >= 6:
                return [parts[1]], int(float(parts[4])) + 1, scan_type

        elif scan_type in ("a2scan", "d2scan"):
            # a2scan m1 s1 e1 m2 s2 e2 npts time
            if len(parts) >= 9:
                return [parts[1], parts[4]], int(float(parts[7])) + 1, scan_type

        elif scan_type in ("a3scan", "d3scan"):
            if len(parts) >= 12:
                return [parts[1], parts[4], parts[7]], int(float(parts[10])) + 1, scan_type

        elif scan_type in ("cscan", "cdscan"):
            # cscan motor center range npts time
            if len(parts) >= 6:
                return [parts[1]], int(float(parts[4])) + 1, scan_type

        elif scan_type == "mesh":
            # mesh m1 s1 e1 n1 m2 s2 e2 n2 time
            if len(parts) >= 10:
                n1 = int(float(parts[4]))
                n2 = int(float(parts[8]))
                return [parts[1], parts[5]], (n1 + 1) * (n2 + 1), scan_type

        elif scan_type == "gscan":
            # gscan motor start end1 step1 [end2 step2 ...] sec
            if len(parts) >= 6:
                motor = parts[1]
                start = float(parts[2])
                # pairs of (end, step) then final count time
                seg_parts = parts[3:-1]
                total = 0
                prev = start
                for i in range(0, len(seg_parts) - 1, 2):
                    end_val = float(seg_parts[i])
                    step_val = float(seg_parts[i + 1])
                    if step_val != 0:
                        total += max(1, round(abs(end_val - prev) / abs(step_val)))
                    prev = end_val
                return [motor], total + 1, scan_type

        elif scan_type == "timescan":
            if len(parts) >= 3:
                return [], int(float(parts[2])), scan_type

    except (ValueError, IndexError):
        pass

    # Fallback: grab motor name if second token isn't a number
    if len(parts) > 1:
        tok = parts[1]
        if not tok.lstrip("-").replace(".", "", 1).isdigit():
            return [tok], None, scan_type
    return [], None, scan_type


def parse_spec_file(filepath: str) -> SpecFile:
    """Parse a SPEC data file into structured Scan objects."""
    with open(filepath, "r", errors="replace") as f:
        lines = f.read().splitlines()

    o_blocks: dict[int, list] = {}   # block_idx -> [motor_names]
    scans: dict[int, Scan] = {}
    current_scan: Optional[Scan] = None
    current_data_lines: list[str] = []
    in_data = False

    def _save_current():
        nonlocal current_scan, current_data_lines, in_data
        if current_scan is None:
            return
        if current_data_lines:
            try:
                current_scan.data = np.array(
                    [[float(x) for x in row.split()] for row in current_data_lines],
                    dtype=np.float64,
                )
            except (ValueError, IndexError):
                current_scan.data = np.empty((0, max(1, current_scan.num_columns)))
        else:
            current_scan.data = np.empty((0, max(1, current_scan.num_columns)))
        scans[current_scan.scan_number] = current_scan
        current_data_lines = []
        in_data = False

    for line in lines:
        stripped = line.rstrip()

        # --- File-level motor name definitions ---
        m = re.match(r"^#O(\d+)\s+(.*)", stripped)
        if m:
            idx = int(m.group(1))
            if idx == 0:
                o_blocks = {}
            o_blocks[idx] = m.group(2).split()
            continue

        # --- New scan ---
        if stripped.startswith("#S "):
            _save_current()
            parts = stripped.split(None, 2)
            try:
                scan_num = int(parts[1])
            except (ValueError, IndexError):
                continue
            command = parts[2] if len(parts) > 2 else ""
            motors, expected, stype = parse_scan_command(command)
            current_scan = Scan(
                scan_number=scan_num,
                command=command,
                scan_type=stype,
                scanned_motors=motors,
                date="",
                motor_positions={},
                column_labels=[],
                num_columns=0,
                data=np.empty((0, 1)),
                expected_points=expected,
            )
            in_data = False
            current_data_lines = []
            continue

        if current_scan is None:
            continue

        # --- Scan-level headers ---
        if stripped.startswith("#D "):
            current_scan.date = stripped[3:]
        elif stripped.startswith("#N "):
            try:
                current_scan.num_columns = int(stripped.split()[1])
            except (ValueError, IndexError):
                pass
        elif stripped.startswith("#L "):
            current_scan.column_labels = stripped[3:].split()
            in_data = True
        elif stripped.startswith("#P"):
            pm = re.match(r"^#P(\d+)\s+(.*)", stripped)
            if pm:
                p_idx = int(pm.group(1))
                positions = pm.group(2).split()
                if p_idx in o_blocks:
                    for j, pos in enumerate(positions):
                        if j < len(o_blocks[p_idx]):
                            try:
                                current_scan.motor_positions[o_blocks[p_idx][j]] = float(pos)
                            except ValueError:
                                pass
        elif stripped.startswith("#"):
            pass
        elif in_data and stripped:
            # Only accept lines that start with a number
            try:
                float(stripped.split()[0])
                current_data_lines.append(stripped)
            except (ValueError, IndexError):
                pass
        elif not stripped and in_data:
            in_data = False

    _save_current()

    motor_names = []
    for idx in sorted(o_blocks.keys()):
        motor_names.extend(o_blocks[idx])

    return SpecFile(filepath=filepath, motor_names=motor_names, scans=scans)
