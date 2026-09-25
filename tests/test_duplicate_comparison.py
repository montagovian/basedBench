"""Embedded-region retrieval must not become redundancy adjudication."""
import random

from PIL import Image, ImageDraw
import pytest

from basedbench.pipeline import duplicate_comparison as experiment


def embedded_pair():
    target = Image.new('RGB', (160, 300), 'white')
    draw = ImageDraw.Draw(target)
    randomizer = random.Random(9)
    for _ in range(30):
        x, y = randomizer.randrange(130), randomizer.randrange(270)
        draw.rectangle((x, y, x + 28, y + 25), fill=tuple(randomizer.randrange(256) for _ in range(3)))
    source = Image.new('RGB', (420, 300), 'black')
    draw = ImageDraw.Draw(source)
    for y in range(0, 300, 10):
        draw.rectangle((0, y, 420, y + 9), fill=(y % 256, 255 - y % 256, 100))
    source.paste(target, (130, 0))
    return (source, source.size), (target, target.size)


def test_nonuniform_borders_are_retrieved_but_not_confirmed():
    left, right = embedded_pair()
    match = experiment.crop_evidence(left, right)
    assert match is not None and match['status'] == 'candidate'
    assert match['pixel_difference'] < .1
    assert match['left_crop'] == [130, 0, 290, 300]
    assert match['right_crop'] == [0, 0, 160, 300]
    inverse = experiment.crop_evidence(right, left)
    assert inverse['left_crop'] == match['right_crop']
    assert inverse['right_crop'] == match['left_crop']


def test_shared_region_does_not_prove_discarded_text_is_irrelevant():
    left, right = embedded_pair()
    ImageDraw.Draw(left[0]).text((5, 5), 'A DIFFERENT JOKE', fill='white')
    assert experiment.crop_evidence(left, right)['status'] == 'candidate'


def test_crop_windows_cannot_use_tiny_common_patches():
    for box in experiment.windows((400, 300), .05):
        assert (box[2] - box[0]) * (box[3] - box[1]) >= .30 * 400 * 300
    assert list(experiment.windows((400, 300), .05)) == []
    with pytest.raises(ValueError):
        list(experiment.windows((400, 300), float('nan')))


def test_missing_and_animated_images_remain_unassessed(tmp_path):
    assert experiment.load_static(tmp_path / 'missing') is None
    path = tmp_path / 'animated.gif'
    Image.new('RGB', (30, 30), 'red').save(path, save_all=True,
        append_images=[Image.new('RGB', (30, 30), 'blue')], duration=100, loop=0)
    assert experiment.load_static(path) is None
    assert experiment.crop_evidence(None, embedded_pair()[0]) is None
