from io import BytesIO
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

from sudoku.vision.reader import read_image, _is_border_fragment

PUZZLE = '530070000600195000098000060800060003400803001700020006060000280000419005000080079'
COLORED_PUZZLE = '147000003250001000309000000080020004000410020900000600003000009400002000001008007'


@pytest.mark.parametrize('scale,format', [(1, 'PNG'), (2, 'PNG'), (1, 'JPEG')])
def test_colored_grid_does_not_invent_digits_from_borders(scale, format):
    with Image.open(Path(__file__).parent / 'fixtures' / 'colored-grid.png') as source:
        image = source.convert('RGB')
        if scale != 1:
            image = image.resize((image.width * scale, image.height * scale))
        output = BytesIO()
        image.save(output, format=format)
    result = read_image(output.getvalue())
    assert result['puzzle'] == COLORED_PUZZLE
    assert result['conflicts'] == []


def test_border_filter_preserves_real_digit_strokes():
    assert _is_border_fragment((61, 0, 1, 20, 20), (62, 62))
    assert _is_border_fragment((0, 60, 40, 2, 80), (62, 62))
    assert not _is_border_fragment((30, 10, 2, 35, 70), (62, 62))
    assert not _is_border_fragment((0, 15, 18, 30, 230), (62, 62))


def puzzle_image(puzzle=PUZZLE, perspective=False):
    image = np.full((800, 800), 255, dtype=np.uint8)
    for n in range(10):
        p = 40 + n * 80
        thickness = 4 if n % 3 == 0 else 2
        cv2.line(image, (40, p), (760, p), 0, thickness)
        cv2.line(image, (p, 40), (p, 760), 0, thickness)
    for i, digit in enumerate(puzzle):
        if digit != '0':
            cv2.putText(image, digit, (64 + i % 9 * 80, 96 + i // 9 * 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.5, 0, 2, cv2.LINE_AA)
    if perspective:
        matrix = cv2.getPerspectiveTransform(np.float32([[0, 0], [799, 0], [799, 799], [0, 799]]),
                                            np.float32([[70, 15], [780, 65], [720, 790], [20, 710]]))
        image = cv2.warpPerspective(image, matrix, (800, 800), borderValue=255)
    return cv2.imencode('.png', image)[1].tobytes()


@pytest.mark.parametrize('perspective', [False, True])
def test_printed_puzzle(perspective):
    result = read_image(puzzle_image(perspective=perspective))
    assert result['puzzle'] == PUZZLE
    assert len(result['cells']) == 81
    assert result['conflicts'] == []
    assert result['preview'].startswith('data:image/png;base64,')


def test_blank_grid_and_duplicate_clues():
    assert read_image(puzzle_image('0' * 81))['puzzle'] == '0' * 81
    result = read_image(puzzle_image('55' + '0' * 79))
    assert result['puzzle'][:2] == '55'
    assert result['conflicts'] == [0, 1]
    assert all(result['cells'][i]['review'] for i in [0, 1])


@pytest.mark.parametrize('data', [b'', b'not an image', b'x' * (8 * 1024 * 1024 + 1)], ids=['empty', 'invalid', 'oversized'])
def test_reject_bad_bytes(data):
    with pytest.raises(ValueError):
        read_image(data)


def test_reject_no_grid_and_large_dimensions():
    for size, message in [((500, 500), 'grid'), ((5000, 4000), 'megapixels')]:
        output = BytesIO()
        Image.new('L', size, 255).save(output, format='PNG')
        with pytest.raises(ValueError, match=message):
            read_image(output.getvalue())
