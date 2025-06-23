import pandas as pd
import numpy as np
import datetime as dt
import textwrap
from io import StringIO

def convert_lcms_csv_to_txtbuffer(csv_bytes, filename="converted.txt") -> StringIO:
    """
    Convert a CSV file with time/signal columns to a Chromeleon-compatible text format.
    
    Parameters:
    -----------
    csv_bytes : bytes
        Raw CSV file content as bytes
    filename : str
        Original filename (used in the header)
        
    Returns:
    --------
    StringIO
        StringIO buffer containing the converted text content
    """
    df = pd.read_csv(
        StringIO(csv_bytes.decode("utf-8")),
        header=None,
        names=["time", "signal"],
        sep=None,
        engine="python"
    ).apply(pd.to_numeric)

    def compute_step(rt):
        diffs = np.diff(rt[:200]) if rt.size > 1 else [0]
        return round(np.median(diffs) * 60.0, 3)

    step_s = compute_step(df["time"].to_numpy())

    now = dt.datetime.now()
    header = textwrap.dedent(f"""\
        Method\tGeneric VWD
        Injection Name\t{filename}
        Operator\t
        Instrument\tName=LCMS, Model=UHPLC, Channel=VWD1A
        Date\t{now:%d.%m.%Y}
        Time\t{now:%H:%M:%S}
        Data Points\t{len(df)}
        Time Range (min)\t{df['time'].iloc[0]:.6f}..{df['time'].iloc[-1]:.6f}
        Step (s)\t{step_s:.3f}
        Signal min (mAU)\t{df['signal'].min():.6f}
        Signal max (mAU)\t{df['signal'].max():.6f}
        """).replace(".", ",") + "Time (min)\tStep (s)\tValue (mAU)\n"

    data_lines = "\n".join(f"{t:.6f}\t{step_s:.3f}\t{v:.6f}" for t, v in zip(df["time"], df["signal"]))
    return StringIO(header + data_lines)