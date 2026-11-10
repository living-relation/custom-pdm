"""Shared geometry for the board B PCB scripts (pcb_board_b.py, route_board_b.py). All mm."""
EXT = 39.0                         # extra board width on the right (72.4 -> 111.4 mm)
SEAM = 7.5                         # strip between the old right edge and the channel blocks: J7, U22 and their parts
SRC_BOX = (5.4, 4.3, 26.6, 25.6)   # the U8 channel block on the board A baseline (x0, y0, x1, y1)
BW, BH = SRC_BOX[3] - SRC_BOX[1], SRC_BOX[2] - SRC_BOX[0]     # block size after the quarter turn (x, y)


def block_centres(x_old, y0, y1):
    """Centre x of the block column and the four centre ys, evenly spread over the board height."""
    gap = (y1 - y0 - 4 * BH) / 5
    return x_old + SEAM + BW / 2, [y0 + gap + BH / 2 + k * (BH + gap) for k in range(4)]
