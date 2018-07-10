import struct
import imghdr


# see https://bugs.python.org/issue16512#msg198034
# not added to imghdr.tests because of potential issues with reloads
def _is_jpg(h):
    return h.startswith(b'\xff\xd8')


def get_image_info(databytes):
    head = databytes[0:32]
    if len(head) != 32:
        return
    what = imghdr.what(None, head)
    if what == 'png':
        check = struct.unpack('>i', head[4:8])[0]
        if check != 0x0d0a1a0a:
            return
        width, height = struct.unpack('>ii', head[16:24])
    elif what == 'gif':
        width, height = struct.unpack('<HH', head[6:10])
    elif what == 'jpeg' or _is_jpg(head):
            pos = 0
            size = 2
            ftype = 0
            while not 0xc0 <= ftype <= 0xcf or ftype in (0xc4, 0xc8, 0xcc):
                pos += size
                byte = databytes[pos:pos + 1]
                while ord(byte) == 0xff:
                    byte = databytes[pos:pos + 1]
                    pos += 1
                ftype = ord(byte)
                size = struct.unpack('>H', databytes[pos:pos + 2])[0] - 2
                pos += 2
            # We are at a SOFn block
            pos += 1  # Skip `precision' byte.
            height, width = struct.unpack('>HH', databytes[pos:pos + 4])

    elif what == "bmp":
        if head[0:2].decode() != "BM":
            return
        width, height = struct.unpack('II', head[18:26])
    else:
        return
    return what, width, height


def image_resize(img_width, img_height, width, height, em_width, max_width, preserve_ratio=1):

    if width:
        if width.isdigit():
            width = int(width) * em_width
        elif width[-1] == "%":
            width = int(img_width * int(width[:-1]) / 100)
    else:
        width = img_width

    if height:
        if height.isdigit():
            height = int(height) * em_width
        elif height[-1] == "%":
            height = int(img_height * int(height[:-1]) / 100)
    else:
        height = img_height

    ratio = img_width / img_height

    if preserve_ratio == 1 or preserve_ratio == "true":
        area = width * height
        height = int((area / ratio) ** 0.5)
        width = int(area / height)

    if width > max_width:
        height = int(height * max_width / width)
        width = max_width

    return (width, height)
