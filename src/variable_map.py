"""Maps iRacing SDK variable names to output CSV column names."""

# Ordered list of (sdk_variable_name, csv_column_name, transform_function)
# Order matches the required CSV column order from OutputDataExample.csv

VARIABLE_MAP = [
    ("Speed",              "Speed",              None),
    ("LapDistPct",         "LapDistPct",         None),
    ("Lat",                "Lat",                None),
    ("Lon",                "Lon",                None),
    ("Brake",              "Brake",              None),
    ("Throttle",           "Throttle",           None),
    ("RPM",                "RPM",                None),
    ("SteeringWheelAngle", "SteeringWheelAngle", None),
    ("Gear",               "Gear",               None),
    ("Clutch",             "Clutch",             None),
    ("BrakeABSactive",     "ABSActive",          lambda v: bool(v)),
    ("DRS_Status",         "DRSActive",          lambda v: v == 3),
    ("LatAccel",           "LatAccel",           None),
    ("LongAccel",          "LongAccel",          None),
    ("VertAccel",          "VertAccel",           None),
    ("Yaw",                "Yaw",                None),
    ("YawRate",            "YawRate",            None),
]

# CSV column headers in exact order
CSV_COLUMNS = [col for _, col, _ in VARIABLE_MAP] + ["PositionType"]
