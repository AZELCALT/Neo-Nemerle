"""Verify .NET strong-name signatures without Mono, sn, or platform SDK tools.

PE/CLI metadata parser for Assembly public key and SHA-1 PKCS#1 v1.5 strong name.
Only SHA-1 signatures are supported, matching Neo-Nemerle's current signer.
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
import struct


class StrongNameError(ValueError):
    """The assembly is unsigned, invalid, unsupported, or has a bad signature."""


def _u1(buf, offset):
    if offset < 0 or offset + 1 > len(buf):
        raise StrongNameError('truncated metadata')
    return buf[offset]


def _u2(buf, offset):
    if offset < 0 or offset + 2 > len(buf):
        raise StrongNameError('truncated metadata')
    return struct.unpack_from('<H', buf, offset)[0]


def _u4(buf, offset):
    if offset < 0 or offset + 4 > len(buf):
        raise StrongNameError('truncated metadata')
    return struct.unpack_from('<I', buf, offset)[0]


def _u8(buf, offset):
    if offset < 0 or offset + 8 > len(buf):
        raise StrongNameError('truncated metadata')
    return struct.unpack_from('<Q', buf, offset)[0]


def _slice(buf, offset, count):
    if offset < 0 or count < 0 or offset + count > len(buf):
        raise StrongNameError('truncated PE image or metadata')
    return buf[offset:offset + count]


def _align(value, alignment):
    return (value + alignment - 1) & -alignment


# Metadata table schema before and including Assembly (table 0x20).
# 'iN': table row index; 'cName': coded index; 's': string heap; 'b': blob;
# 'g': GUID heap; '2','4': primitive size.
_TABLES = [
    '2 s g g g',              # Module
    'cResolutionScope s s',  # TypeRef
    '4 s s cTypeDefOrRef i4 i6', # TypeDef
    'i4', '2 s b', 'i6',
    '4 2 2 s b i8',           # MethodDef
    'i8', '2 2 s', 'i2 cTypeDefOrRef',
    'cMemberRefParent s b',  # MemberRef
    '2 cHasConstant b',
    'cHasCustomAttribute cCustomAttributeType b',
    'cHasFieldMarshal b',
    '2 cHasDeclSecurity b',
    '2 4 i2', '4 i4', 'b',
    'i2 i20', 'i20', '2 s cTypeDefOrRef',
    'i2 i23', 'i23', '2 s b',
    '2 i6 cHasSemantics',
    'i2 cMethodDefOrRef cMethodDefOrRef',
    's', 'b', '2 cMemberForwarded s i26',
    '4 i4', '4 4', '4',
    '4 2 2 2 2 4 b s s',
]
_CODED = {
    'ResolutionScope': (2, [0, 26, 35, 1]),
    'TypeDefOrRef': (2, [2, 1, 27]),
    'MemberRefParent': (3, [2, 1, 26, 6, 27]),
    'HasConstant': (2, [4, 8, 23]),
    'HasCustomAttribute': (5, [6, 4, 1, 2, 8, 9, 10, 0, 14, 23, 20, 17, 26, 27, 32, 35, 38, 39, 40, 42, 44, 43]),
    'CustomAttributeType': (3, [6, 10]),
    'HasFieldMarshal': (1, [4, 8]),
    'HasDeclSecurity': (2, [2, 6, 32]),
    'HasSemantics': (1, [20, 23]),
    'MethodDefOrRef': (1, [6, 10]),
    'MemberForwarded': (1, [4, 6]),
}


def _public_key(data, meta_offset, meta_size):
    root = _slice(data, meta_offset, meta_size)
    if _u4(root, 0) != 0x424A5342:
        raise StrongNameError('invalid CLR metadata signature')
    version_bytes = _u4(root, 12)
    offset = _align(16 + version_bytes, 4)
    streams = _u2(root, offset + 2)
    offset += 4
    found = {}
    for _ in range(streams):
        start = _u4(root, offset)
        count = _u4(root, offset + 4)
        name_begin = offset + 8
        end = root.find(b'\0', name_begin, min(name_begin + 64, len(root)))
        if end < 0:
            raise StrongNameError('invalid metadata stream header')
        name = root[name_begin:end].decode('ascii')
        found[name] = _slice(root, start, count)
        offset = _align(end + 1, 4)
    tables = found.get('#~', found.get('#-'))
    blobs = found.get('#Blob')
    if tables is None or blobs is None:
        raise StrongNameError('missing CLR metadata tables or blob heap')
    heaps = _u1(tables, 6)
    valid = _u8(tables, 8)
    row_counts = [0] * 64
    off = 24
    for index in range(64):
        if valid & (1 << index):
            row_counts[index] = _u4(tables, off)
            off += 4
    if row_counts[32] != 1:
        raise StrongNameError('assembly manifest must have one Assembly row')

    def width(column):
        if column == '2' or column == '4':
            return int(column)
        if column in ('s', 'g', 'b'):
            return 4 if heaps & {'s': 1, 'g': 2, 'b': 4}[column] else 2
        if column[0] == 'i':
            return 4 if row_counts[int(column[1:])] >= 1 << 16 else 2
        if column[0] == 'c':
            tag_bits, possible_tables = _CODED[column[1:]]
            return 4 if max(row_counts[t] for t in possible_tables) >= 1 << (16-tag_bits) else 2
        raise StrongNameError(f'unknown metadata column: {column}')

    for table_index in range(32):
        if row_counts[table_index]:
            off += row_counts[table_index] * sum(width(col) for col in _TABLES[table_index].split())
    if off >= len(tables):
        raise StrongNameError('truncated Assembly metadata row')
    row = _TABLES[32].split()
    hash_id = _u4(tables, off)
    if hash_id not in (0, 0x8004):
        raise StrongNameError(f'unsupported strong-name hash algorithm: 0x{hash_id:x}')
    key_col_offset = off + sum(width(x) for x in row[:6])
    key_index = _u4(tables, key_col_offset) if width('b') == 4 else _u2(tables, key_col_offset)
    if not key_index:
        raise StrongNameError('assembly manifest has no public key')
    first = _u1(blobs, key_index)
    if first & 0x80 == 0:
        count, consumed = first, 1
    elif first & 0xC0 == 0x80:
        count, consumed = ((first & 0x3f) << 8) | _u1(blobs, key_index + 1), 2
    elif first & 0xE0 == 0xC0:
        count, consumed = ((first & 0x1f) << 24) | (_u1(blobs, key_index + 1) << 16) | (_u1(blobs, key_index + 2) << 8) | _u1(blobs, key_index + 3), 4
    else:
        raise StrongNameError('invalid compressed blob length')
    key = _slice(blobs, key_index + consumed, count)
    if len(key) < 32:
        raise StrongNameError('truncated RSA public key')
    sig_algorithm = _u4(key, 0)
    key_size = _u4(key, 8)
    if len(key) != 12 + key_size or _u1(key, 12) != 6 or _u4(key, 20) != 0x31415352:
        raise StrongNameError('unsupported RSA public key blob')
    if sig_algorithm not in (0, 0x2400):
        raise StrongNameError(f'unsupported public key algorithm: 0x{sig_algorithm:x}')
    bits = _u4(key, 24)
    exponent = _u4(key, 28)
    if not bits or bits % 8 or exponent < 3 or not exponent & 1:
        raise StrongNameError('invalid RSA key dimensions')
    modulus = int.from_bytes(_slice(key, 32, bits // 8), 'little')
    if len(key) != 32 + bits // 8 or modulus.bit_length() < bits - 8:
        raise StrongNameError('invalid RSA modulus')
    return modulus, exponent, bits // 8


def verify_strong_name(assembly: Path | str) -> None:
    """Raise StrongNameError unless an assembly's embedded RSA key verifies its strong name."""
    data = Path(assembly).read_bytes()
    if _slice(data, 0, 2) != b'MZ':
        raise StrongNameError('not a PE image')
    pe = _u4(data, 0x3c)
    if _slice(data, pe, 4) != b'PE\0\0':
        raise StrongNameError('invalid PE header')
    num_sections = _u2(data, pe + 6)
    opt = pe + 24
    opt_size = _u2(data, pe + 20)
    magic = _u2(data, opt)
    if magic not in (0x10b, 0x20b):
        raise StrongNameError('unsupported PE format')
    directories = opt + (96 if magic == 0x10b else 112)
    if opt_size < directories - opt + 15 * 8:
        raise StrongNameError('missing CLI data directory')
    section_table = opt + opt_size
    end_headers = section_table + num_sections * 40
    _slice(data, section_table, num_sections * 40)

    def rva_offset(rva, size):
        for section in range(num_sections):
            sh = section_table + 40 * section
            virtual_size, va = _u4(data, sh + 8), _u4(data, sh + 12)
            raw_size, raw_offset = _u4(data, sh + 16), _u4(data, sh + 20)
            if va <= rva and rva + size <= va + max(virtual_size, raw_size) and rva + size <= va + raw_size:
                mapped = raw_offset + rva - va
                _slice(data, mapped, size)
                return mapped
        raise StrongNameError('RVA is not mapped to section bytes')

    cli_rva, cli_size = _u4(data, directories + 14 * 8), _u4(data, directories + 14 * 8 + 4)
    if cli_size < 40:
        raise StrongNameError('missing CLI header')
    cli = rva_offset(cli_rva, cli_size)
    md_rva, md_size = _u4(data, cli + 8), _u4(data, cli + 12)
    if not (_u4(data, cli + 16) & 8):
        raise StrongNameError('assembly is not marked StrongNameSigned')
    sig_rva, sig_size = _u4(data, cli + 32), _u4(data, cli + 36)
    if not sig_size:
        raise StrongNameError('assembly has no strong-name signature')
    sig_off = rva_offset(sig_rva, sig_size)
    signature = _slice(data, sig_off, sig_size)
    if not any(signature):
        raise StrongNameError('assembly has an empty strong-name signature')
    n, e, width = _public_key(data, rva_offset(md_rva, md_size), md_size)
    if sig_size != width:
        raise StrongNameError('strong-name slot length differs from RSA modulus length')

    # ECMA-335 II.6.2.3: hash PE headers with checksum and security directory zero,
    # and the section bytes in file order, treating the strong-name signature slot as zeros.
    # The signer in platform/ClrCompilerSection.cs uses the same layout when these fields are already zero.
    section_ranges = []
    for section in range(num_sections):
        sh = section_table + section * 40
        length, start = _u4(data, sh + 16), _u4(data, sh + 20)
        if length:
            _slice(data, start, length)
            section_ranges.append((start, start + length))
    section_ranges.sort()
    if not any(start <= sig_off and sig_off + sig_size <= end for start, end in section_ranges):
        raise StrongNameError('signature does not reside entirely in one PE section')
    if any(section_ranges[i][1] > section_ranges[i+1][0] for i in range(len(section_ranges)-1)):
        raise StrongNameError('overlapping PE sections')

    h = hashlib.sha1()
    hdr = bytearray(_slice(data, 0, end_headers))
    hdr[opt + 64:opt + 68] = b'\x00' * 4  # PE checksum
    hdr[directories + 32:directories + 40] = b'\x00' * 8  # Authenticode certificate table
    h.update(hdr)
    for start, end in section_ranges:
        # ECMA-335/.NET: OMIT the strong-name signature bytes from the hash.
        # Replacing the signature with zero bytes changes the hash and rejects
        # assemblies correctly signed by Roslyn, Mono, and Neo-Nemerle.
        if start <= sig_off < end:
            h.update(data[start:sig_off])
            h.update(data[sig_off + sig_size:end])
        else:
            h.update(data[start:end])
    digest = h.digest()
    sha1_der = bytes.fromhex('3021300906052b0e03021a05000414')
    expected_tail = sha1_der + digest
    padding_len = width - len(expected_tail) - 3
    if padding_len < 8:
        raise StrongNameError('RSA modulus too short for strong-name signature')
    expected = b'\x00\x01' + b'\xff' * padding_len + b'\x00' + expected_tail
    signature_value = int.from_bytes(signature[::-1], 'big')
    if signature_value >= n:
        raise StrongNameError('signature is outside modulus')
    actual = pow(signature_value, e, n).to_bytes(width, 'big')
    if not hmac.compare_digest(actual, expected):
        raise StrongNameError(f'invalid strong-name signature: {assembly}')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('assembly', nargs='+', type=Path)
    a = p.parse_args()
    for file in a.assembly:
        verify_strong_name(file)
        print('PASS: strong-name signature', file)
