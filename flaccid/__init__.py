from typing import List, Text, Optional
from ctypes import sizeof, LittleEndianStructure, BigEndianStructure, c_uint8, c_uint16, c_uint32, c_uint64
from enum import Enum


class MetadataBlockType(Enum):
    STREAMINFO = 0
    PADDING = 1
    APPLICATION = 2
    SEEKTABLE = 3
    VORBIS_COMMENT = 4
    CUESHEET = 5
    PICTURE = 6
    # types 7 through 126 are reserved
    INVALID = 127


class MetadataBlockHeader(BigEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('is_last_block', c_uint32, 1),
        ('block_type', c_uint32, 7),
        ('length', c_uint32, 24),
    ]


class MetadataBlockData(BigEndianStructure):
    _pack_ = 1


# some blocks are big endian, like vorbis comment blocks
class MetadataBlockDataLittleEndian(LittleEndianStructure):
    _pack_ = 1


class MetadataBlockStreamInfo(MetadataBlockData):
    _fields_ = [
        ('min_block_size', c_uint16, 16),
        ('max_block_size', c_uint16, 16),
        ('min_frame_size', c_uint32, 24),
        ('max_frame_size', c_uint32, 24),
        ('sample_rate_hz', c_uint32, 20),
        ('num_channels', c_uint8, 3),
        ('bits_per_sample', c_uint8, 5),
        ('total_sample_count', c_uint64, 36),
        ('md5_low', c_uint64, 64),
        ('md5_high', c_uint64, 64),
    ]


class MetadataBlock(object):
    def __init__(self, header, data):
        # type: (MetadataBlockHeader, MetadataBlockData) -> None
        self.header = header
        self.data = data


class MetadataSeekPoint(MetadataBlockData):
    _fields_ = [
        ('first_sample_number', c_uint64, 64),
        ('target_offset', c_uint64, 64),
        ('target_num_samples', c_uint16, 16),
    ]


class MetadataBlockSeekTable(MetadataBlockData):
    def __init__(self, seek_points):
        # type: (List[MetadataSeekPoint]) -> None
        self.seek_points = seek_points


class MetadataBlockVorbisComment(MetadataBlockDataLittleEndian):
    def __init__(self, vendor_string, user_comments):
        # type: (Text, List[Text]) -> None
        self.vendor_string = vendor_string
        self.user_comments = user_comments


class MetadataBlockPadding(MetadataBlock):
    def __init__(self, length):
        self.length = length


class FrameHeaderRaw(BigEndianStructure):
    SYNC_CODE = '0b11111111111110'

    _pack_ = 1
    _fields_ = [
        ('sync_code', c_uint16, 14),
        ('reserved1', c_uint8, 1),
        ('blocking_strategy', c_uint8, 1),
        ('block_size', c_uint8, 4),
        ('sample_rate', c_uint8, 4),
        ('channel', c_uint8, 4),
        ('sample_size', c_uint8, 3),
        ('reserved2', c_uint8, 1),
    ]
class FrameHeader(object):
    def __init__(self, raw_header):
        # type: (FrameHeaderRaw) -> None
        self.raw_header = raw_header
        self.validate_header()
    def validate_header(self):
        if self.raw_header.reserved1 != 0:
            raise RuntimeError('frame_header->reserved1 was not 0!')
        if self.raw_header.reserved2 != 0:
            raise RuntimeError('frame_header->reserved2 was not 0!')


class FlacParser(object):
    def __init__(self, flac_file):
        # type: (file) -> None
        self.flac = flac_file
        self.parse_magic()

        # FLAC guarantees at least one metadata block; the stream info block
        self.metadata_blocks = []
        while True:
            try:
                metadata_block = self.parse_metadata_block()
                self.metadata_blocks.append(metadata_block)
            except NotImplementedError:
                print('Parsed up to unknown metadata block type, stopping here')
                break

            if metadata_block.header.is_last_block:
                break
        print('Finished parsing {} metadata blocks'.format(len(self.metadata_blocks)))

        self.stream_info = self.get_metadata_block_with_type(MetadataBlockType.STREAMINFO)
        self.seek_table = self.get_metadata_block_with_type(MetadataBlockType.SEEKTABLE)
        self.vorbis_comments = self.get_metadata_block_with_type(MetadataBlockType.VORBIS_COMMENT)

        self.dump_stream_info()
        self.dump_seek_table()
        self.dump_vorbis_comments()

        frame_header = self.parse_frame_header()
        print('frame header blocking strategy {} block size {}'.format(frame_header.blocking_strategy.name, frame_header.block_size))
        print('got frame header! blocking strategy {} block size {} sample rate {} channels {} sample size {} '.format(
            frame_header.blocking_strategy,
            frame_header.block_size,
            frame_header.sample_rate,
            frame_header.channels,
            frame_header.sample_size,
        ))

    def parse_frame_header(self):
        # type: () -> FrameHeader
        raw_header_bytes = bytearray(bytes(self.flac.read(sizeof(FrameHeaderRaw))))
        raw_header = FrameHeaderRaw.from_buffer(raw_header_bytes)
        if bin(raw_header.sync_code) != FrameHeaderRaw.SYNC_CODE:
            raise RuntimeError('FrameHeader sync code was incorrect (got {})'.format(bin(raw_header.sync_code)))
        return FrameHeader(raw_header)

    def get_metadata_block_with_type(self, block_type):
        # type: (MetadataBlockType) -> Optional[MetadataBlock]
        for x in self.metadata_blocks:
            if x.header.block_type == block_type.value:
                return x
        return None

    def dump_stream_info(self):
        print('FLAC ({}) audio stream info:'.format(self.flac.name))

        print('\tSmallest block size: {}'.format(self.stream_info.data.min_block_size))
        print('\tLargest block size: {}'.format(self.stream_info.data.max_block_size))
        print('\tSmallest frame size: {}'.format(self.stream_info.data.min_frame_size))
        print('\tLargest frame size: {}'.format(self.stream_info.data.max_frame_size))
        print('\tSample rate (in Hz): {}'.format(self.stream_info.data.sample_rate_hz))
        print('\tChannel count: {}'.format(self.stream_info.data.num_channels))
        print('\tBits per sample: {}'.format(self.stream_info.data.bits_per_sample))
        print('\tTotal sample count: {}'.format(self.stream_info.data.total_sample_count))

        md5_sig = str(self.stream_info.data.md5_low) + str(self.stream_info.data.md5_high)
        print('\tMD5 signature of audio stream: {}'.format(md5_sig))

    def dump_seek_table(self):
        print('Seek table ({} entries):'.format(len(self.seek_table.data.seek_points)))
        for i, seek_point in enumerate(self.seek_table.data.seek_points):
            print('\tseek point {}:'.format(i))
            print('\t\tFirst sample number: {}'.format(seek_point.first_sample_number))
            print('\t\tTarget sample offset: {}'.format(seek_point.target_offset))
            print('\t\tTarget sample count: {}'.format(seek_point.target_num_samples))

    def dump_vorbis_comments(self):
        comments = self.vorbis_comments.data
        print('{} Vorbis comments. Vendor: {}'.format(len(comments.user_comments), comments.vendor_string))
        for comment in comments.user_comments:
            print('\t{}'.format(comment))

    def parse_magic(self):
        correct_magic = b'fLaC'
        magic = self.flac.read(4)
        for i, b in enumerate(magic):
            if b is not correct_magic[i]:
                print('incorrect magic byte {}, expected {}'.format(b, correct_magic[i]))
        print('FLAC magic verified')

    def parse_metadata_header(self):
        header_bytes = bytearray(bytes(self.flac.read(sizeof(MetadataBlockHeader))))
        header = MetadataBlockHeader.from_buffer(header_bytes)
        return header

    def read_ctype_from_file(self, ctype_type):
        raw_bytes = bytearray(bytes(self.flac.read(sizeof(ctype_type))))
        return ctype_type.from_buffer(raw_bytes)

    def parse_seektable(self, header):
        # type: (MetadataBlockHeader) -> MetadataBlockSeekTable
        if header.block_type != MetadataBlockType.SEEKTABLE.value:
            raise RuntimeError('wrong header passed to parse_seektable()')
        # each SeekPoint is 18 bytes as defined by the standard
        if sizeof(MetadataSeekPoint) != 18:
            raise RuntimeError('bad seekpoint def? not 18 bytes, {}'.format(sizeof(MetadataSeekPoint)))
        seekpoint_count = int(header.length / 18)
        seekpoints = []
        for i in range(seekpoint_count):
            seekpoint = self.read_ctype_from_file(MetadataSeekPoint)
            seekpoints.append(seekpoint)
        return MetadataBlockSeekTable(seekpoints)

    def parse_vorbis_comment(self, header):
        # type: (MetadataBlockHeader) -> MetadataBlockVorbisComment
        if header.block_type != MetadataBlockType.VORBIS_COMMENT.value:
            raise RuntimeError('wrong header passed to parse_vorbis_comment()')
        vendor_length = self.read_ctype_from_file(c_uint32).value
        vendor_string = self.flac.read(vendor_length).decode('utf-8')
        user_comment_list_len = self.read_ctype_from_file(c_uint32).value
        user_comments = []
        for i in range(user_comment_list_len):
            user_comment_len = self.read_ctype_from_file(c_uint32).value
            user_comment = self.flac.read(user_comment_len).decode('utf-8')
            user_comments.append(user_comment)
        return MetadataBlockVorbisComment(vendor_string, user_comments)

    def parse_padding(self, header):
        # type: (MetadataBlockHeader) -> MetadataBlockPadding
        if header.block_type != MetadataBlockType.PADDING.value:
            raise RuntimeError('wrong header passed to parse_padding()')
        return MetadataBlockPadding(header.length)

    def parse_data_for_metadata_header(self, header):
        # type: (MetadataBlockHeader) -> MetadataBlockData
        if header.block_type == MetadataBlockType.STREAMINFO.value:
            data_type = MetadataBlockStreamInfo
        elif header.block_type == MetadataBlockType.SEEKTABLE.value:
            return self.parse_seektable(header)
        elif header.block_type == MetadataBlockType.VORBIS_COMMENT.value:
            return self.parse_vorbis_comment(header)
        elif header.block_type == MetadataBlockType.PADDING.value:
            return self.parse_padding(header)
        else:
            raise NotImplementedError('block type {}'.format(header.block_type))
        return self.read_ctype_from_file(data_type)

    def parse_metadata_block(self):
        header = self.parse_metadata_header()
        block_end = self.flac.tell() + header.length
        print('Parsing {} metadata block ({} bytes)'.format(MetadataBlockType(header.block_type).name, header.length))
        if header.is_last_block:
            print('This is the last metadata block before audio blocks')
        data = self.parse_data_for_metadata_header(header)

        # seek to beginning of next block
        self.flac.seek(block_end)

        return MetadataBlock(header, data)

file = 'Bombtrack.flac'
with open(file, 'rb') as flac_file:
    parser = FlacParser(flac_file)


