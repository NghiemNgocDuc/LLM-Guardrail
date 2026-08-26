"""
    PngWriter

A zero-dependency PNG encoder (truecolor RGB, 8-bit) used by the
analytics chart renderer. Only Julia stdlibs are used:

  * deflate is written as STORED blocks (valid DEFLATE), so no zlib
    dependency is needed; the zlib wrapper carries an adler32 checksum
  * the PNG chunk CRC-32 (IEEE) is computed with a hand-rolled table

Charts produced here are verified by tests at the pixel level (bar tops
must land on hand-calculated rows), so the encoder is deliberately
deterministic: identical input always yields identical bytes.
"""
module PngWriter

export write_png, png_header

# pixel type: RGB triple, row-major image as Matrix{NTuple{3,UInt8}} (img[y, x])
const Pixel = NTuple{3,UInt8}

# ── endian helpers ───────────────────────────────────────────────────────
be32_bytes(x::UInt32) = UInt8[(x >> 24) & 0xFF, (x >> 16) & 0xFF, (x >> 8) & 0xFF, x & 0xFF]
be16_bytes(x::UInt16) = UInt8[(x >> 8) & 0xFF, x & 0xFF]
le16_bytes(x::UInt16) = UInt8[x & 0xFF, (x >> 8) & 0xFF]  # deflate stored LEN/NLEN is LE

# ── CRC-32 (IEEE) ────────────────────────────────────────────────────────────
const _CRC_TABLE = let table = zeros(UInt32, 256)
    for n in 0:255
        c = UInt32(n)
        for _ in 1:8
            c = (c & 0x01) != 0 ? 0xEDB88320 ⊻ (c >> 1) : c >> 1
        end
        table[n+1] = c
    end
    table
end

function crc32(data::AbstractVector{UInt8})
    c = UInt32(0xFFFFFFFF)
    for b in data
        c = _CRC_TABLE[((c ⊻ UInt32(b)) & 0xFF) + 1] ⊻ (c >> 8)
    end
    return c ⊻ 0xFFFFFFFF
end

# ── adler32 ──────────────────────────────────────────────────────────────────
function adler32(data::AbstractVector{UInt8})
    a = UInt32(1)
    b = UInt32(0)
    for byte in data
        a = (a + UInt32(byte)) % 0xFFF1
        b = (b + a) % 0xFFF1
    end
    return (b << 16) | a
end

# ── deflate: stored blocks + zlib wrapper ────────────────────────────────────
function zlib_stored(data::AbstractVector{UInt8})
    out = UInt8[]
    # zlib header: CMF=0x78 (deflate, 32K window), FLG=0x01 (FCHECK valid)
    append!(out, UInt8[0x78, 0x01])
    n = length(data)
    pos = 1
    while n - pos + 1 > 0
        chunk = min(65535, n - pos + 1)
        final = pos + chunk - 1 == n ? 0x01 : 0x00
        len = UInt16(chunk)
        push!(out, final)          # BFINAL + BTYPE=00 (stored)
        append!(out, le16_bytes(len))
        append!(out, le16_bytes(UInt16(⊻(len, 0xFFFF))))
        append!(out, data[pos:pos+chunk-1])
        pos += chunk
    end
    append!(out, be32_bytes(adler32(data)))
    return out
end

# ── PNG chunk framing ────────────────────────────────────────────────────────
function png_chunk(type::AbstractString, payload::AbstractVector{UInt8})
    out = UInt8[]
    append!(out, be32_bytes(UInt32(length(payload))))
    type_bytes = collect(codeunits(type))
    append!(out, type_bytes)
    append!(out, payload)
    append!(out, be32_bytes(crc32(vcat(type_bytes, payload))))
    return out
end

"""
    png_header(width, height) -> Vector{UInt8}

The 8-byte PNG signature (verifiable by tests).
"""
png_header(::Any, ::Any) = UInt8[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]

"""
    write_png(path, img::Matrix{Pixel}; width=size(img,2), height=size(img,1))

Encode `img` (row-major, `img[y, x]`) as an RGB PNG. Rows are stored
top-down with filter type 0, exactly as PNG expects.
"""
function write_png(path::AbstractString, img::Matrix{Pixel})
    h, w = size(img)
    ihdr = UInt8[]
    append!(ihdr, be32_bytes(UInt32(w)))
    append!(ihdr, be32_bytes(UInt32(h)))
    append!(ihdr, UInt8[0x08, 0x02, 0x00, 0x00, 0x00]) # bit depth 8, color type 2 (RGB)

    scanlines = UInt8[]
    sizehint!(scanlines, h * (1 + 3w))
    for y in 1:h
        push!(scanlines, 0x00) # filter: none
        for x in 1:w
            r, g, b = img[y, x]
            push!(scanlines, r, g, b)
        end
    end

    io = IOBuffer()
    write(io, png_header(w, h))
    write(io, png_chunk("IHDR", ihdr))
    write(io, png_chunk("IDAT", zlib_stored(scanlines)))
    write(io, png_chunk("IEND", UInt8[]))
    return write(path, take!(io))
end

end # module PngWriter