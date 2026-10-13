# Shimadzu LabSolutions .lcd: raw PDA data (work in progress)

Status 2026-10-13: the container and most of the PDA frame codec are understood; the raw matrix is **not** yet
readable end to end, so nothing in the app reads signal from an `.lcd`. Only the method is read (see
`src/services/shimadzu_method.py`). Needed to finish: one `.lcd` and the text export of the **same injection**
(the export holds the full 3D matrix as ground truth).

Reference file used: `BZ-AMINE-STANDR2.lcd` (no export available).

## Container

OLE2 compound file (`olefile`). Streams that matter:

| Stream | Content |
|---|---|
| `PDA 3D Raw Data/3D Raw Data` | the matrix, 7201 frames (spectra), see below |
| `PDA 3D Raw Data/3D Data Item` | XML: `CN` spectra count (7201), `ECN` 412 wavelengths, `ELE/DT` the 412 wavelengths as little-endian float64 in 0.01 nm (188.88, 190.18 ... 700.91; the spacing is not uniform), `WVB`/`WVE` 190/700 nm, units: raw = **uAU** (`VF` 1), mAU = 1000 uAU, AU = 1e6 |
| `PDA 3D Raw Data/Status` | int32: 1, 7201, 19000, 70000, 0, 180000 (ms), 25 (ms interval) |
| `LSS Raw Data/StatusLog Ch*`, `Max Plot` | same `RC` frame family (status traces, max-absorbance plot), compressed |
| `GUMM_Information/.../*.METHOD` | the method as run (already read) |

## Frame layout (`3D Raw Data`)

The stream is a plain concatenation of frames, each starting `52 43 00 00` ("RC"):

```
int32 magic 0x4352 | int32 1 | int32 412 | int32 frame_length | 8 zero bytes | payload | 1 trailer byte (0 or 1)
```

Frames 0 and 1 are all zero (412 zero bytes). The frame lengths add up exactly to the stream size.

Payload (understood):
- `uint16 LE` reference value, then **256 delta tokens**, giving 257 values along the wavelength axis.
- Token = prefix code by the top 3 bits of the first byte: `0x00-0x1f` 1 byte, 5-bit signed; `0x20-0x3f` 2 bytes, 13-bit signed;
  `0x40-0x5f` 3 bytes, 21-bit signed; `0x60-0x7f` 4 bytes, 29-bit signed.
- Then the same `uint16` reference value again, then 158 or 159 more tokens; the **last token repeats the first one of this second
  group** in every frame checked (frames 888, 2000, 5070).

What supports the decoding: the value at wavelength index 25 across all frames gives a real chromatogram (a strong peak at
0.37 min, a second at 2.1 min, a rising gradient baseline), values in uAU.

## Open questions

1. How the second group maps to wavelengths 257..411 (155 values) and what the extra 3-4 tokens and the repeated first token are
   (a step, a correction, or a check value). With 412 expected values, 257 + 155 = 412 only if the extras are not data.
2. The meaning of the reference value (equal in both groups).
3. Whether the first value after the reference is the 188.88 nm point (it behaves like a very large first delta).

All three are settled by comparing the decoded frames with the `[PDA 3D]` section of the text export of the same run.
