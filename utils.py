# packet handler
class PacketHandler:
    def __init__(self):
        super(PacketHandler, self).__init__()
        self.__cmd_pkt_header = {'upload': b'\x00', 'download': b'\x01'}
        self.__port_pkt_header = b'\x20'
        self.__seg_pkt_header = b'\x40'
        self.__sig_pkt_header = {'start': b'\x60', 'eof': b'\x61', 'exit': b'\x62'}
        self.__ack_pkt_header = b'\x80'

    def pack_seg(self, seq_num: int, seg: bytes):
        return self.__seg_pkt_header + seq_num.to_bytes(4, 'little', signed=True) + seg

    def unpack_seg(self, seg_pkt: bytes):
        assert self.is_seg_pkt(seg_pkt)
        return int.from_bytes(seg_pkt[1:5], 'little', signed=True), seg_pkt[5:]

    def pack_sig(self, sig: str):
        return self.__sig_pkt_header[sig]

    def unpack_sig(self, sig_pkt: bytes):
        assert self.is_sig_pkt(sig_pkt)
        for k, v in self.__sig_pkt_header.items():
            if sig_pkt == v:
                return k

    def pack_port(self, port: int):
        return self.__port_pkt_header + port.to_bytes(2, 'little', signed=False)

    def unpack_port(self, port_pkt: bytes):
        assert self.is_port_pkt(port_pkt)
        return int.from_bytes(port_pkt[1:], 'little', signed=False)

    def pack_cmd(self, command: str, file_path: str):
        return self.__cmd_pkt_header[command] + file_path.encode('utf-8')

    def unpack_cmd(self, cmd_pkt: bytes):
        assert self.is_cmd_pkt(cmd_pkt)
        for k, v in self.__cmd_pkt_header.items():
            if cmd_pkt[:1] == v:
                return k, cmd_pkt[1:].decode('utf-8')

    def pack_ack(self, ack: int, real_seq: int):
        return self.__ack_pkt_header + \
               ack.to_bytes(4, 'little', signed=True) + \
               real_seq.to_bytes(4, 'little', signed=True)

    def unpack_ack(self, ack_pkt: bytes):
        assert self.is_ack_pkt(ack_pkt)
        return int.from_bytes(ack_pkt[1:5], 'little', signed=True), int.from_bytes(ack_pkt[5:], 'little', signed=True)

    def is_cmd_pkt(self, pkt: bytes):
        return pkt[:1] == b'\x01' or pkt[:1] == b'\x00'

    def is_port_pkt(self, pkt: bytes):
        return pkt[:1] == b'\x20'

    def is_seg_pkt(self, pkt: bytes):
        return pkt[:1] == b'\x40'

    def is_sig_pkt(self, pkt: bytes):
        return pkt[:1] == b'\x60' or pkt[:1] == b'\x61' or pkt[:1] == b'\x62'

    def is_ack_pkt(self, pkt: bytes):
        return pkt[:1] == b'\x80'


packer = PacketHandler()
