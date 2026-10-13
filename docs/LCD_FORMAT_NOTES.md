# Shimadzu LabSolutions .lcd (raw data file)

Status 2026-10-13: **read in full** by `src/services/lcd_reader.py` and ingested by `src/ingestion/presets/shimadzu_lcd.py`.
Verified against the ASCII exports of the same injections: for all 7 alanine calibration runs every one of the 8401 spectra
(412 points each) is identical to the export's `[PDA 3D]` matrix, the exported channels reproduce to the last digit, and the
sample record matches. All 39 `.lcd` files on the group share (3, 7 and 10 min runs) open.

Not read yet: LabSolutions' own peak tables (`LSS Data Processing/PT-PDA.1.1.PDA.1.<n>`), the MS data of LC-MS runs.

An `.lcd` is an OLE2 compound file (`olefile`). What is where:

| Stream | Content |
|---|---|
| `PDA 3D Raw Data/3D Raw Data` | the matrix, one frame per spectrum |
| `PDA 3D Raw Data/3D Data Item` | XML: `CN` spectra, `ELE/DT` the wavelengths (float64, hundredths of nm, not uniformly spaced), `WVB`/`WVE` scan range; the raw unit is micro-AU (mAU = raw / 1000) |
| `PDA 3D Raw Data/Status` | int32: 1, spectra, 19000, 70000, 0, run length in ms, interval in ms |
| `LSS Data Processing/SD-PDA.1.1.PDA.1.<n>` | existence = channel n is exported; `Multi Chromato Table` int32 record n (8 ints from index 4): wavelength in hundredths of nm, `flags & 0xFF` = bandwidth |
| `LSS Raw Data/StatusLog Ch<n>` and `2D Data Item` | pump pressure, temperatures: frames like the PDA ones, factor `CF`, unit factor `VF` (bar = kgf/cm2 / VF), names by `DSID` |
| `File Property` | XML: `SampleInfo` (hex-coded text: name, type, vial, level, operator; amounts; acquired), `SampleInfoFile` (data, method and batch paths), created and saved times |
| `GUMM_Information/*` | the instrument method as run (`shimadzu_method.py`), `<IN>` instrument name |

## Frame codec

A stream is a plain concatenation of frames:

```
int32 0x4352 'RC' | int32 1 | int32 n_values | int32 frame_length | 8 zero bytes
group A: uint16 L | L bytes of tokens | uint16 L          (the first 256 values)
group B: uint16 L | L bytes of tokens | uint16 L          (the remaining n_values - 256)
```

Every group is a running sum of signed deltas that starts at zero. A token is a prefix code on the top three bits of its
first byte: `000` 1 byte (5 signed bits), `001` 2 bytes (13 bits), `010` 3 bytes (21 bits), `011` 4 bytes (29 bits).
Status traces use the same groups (one group while there are at most 256 readings, two above), with a 24-byte header.

Channel chromatograms are not stored: they are the mean of the spectrum columns within wavelength +/- bandwidth, rounded
half up. The text export repeats the first status reading of a short trace; the reader does the same so both agree.

## How it was found

Frame lengths add up exactly to the stream size; the first and second frame are all zero; the delta prefix code was the
only reading under which every frame ends exactly where it declares; then the decoded matrix was compared with the export.
