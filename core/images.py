"""Images dragged into the terminal.
"""
import base64
import mimetypes
import os
import re
import urllib.parse

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

# Where a path ends: an image extension not followed by more of a name.
EXTENSION = re.compile(r"\.(?:png|jpe?g|webp|gif)(?![\w])", re.IGNORECASE)


def as_path(text):
    if text.startswith("file://"):
        text = urllib.parse.unquote(urllib.parse.urlparse(text).path)
    return os.path.expanduser(text.replace("\\ ", " "))


def find_path(text, end):
    """(start, path): the longest run of text ending at end that names an
    existing file, or None.

    Quotes cannot be trusted to delimit a path - "what's on '/x/a b.png'"
    pairs the apostrophe with the path's opening quote - so every place a
    path could start (the beginning, or just after a space or quote) is
    tried, the farthest first, and the file system decides.
    """
    for start in range(end):
        if start and not (text[start - 1].isspace() or text[start - 1] in "'\"`("):
            continue
        path = as_path(text[start:end])
        if os.path.isfile(path):
            return start, path
    return None


def extract_images(text):
    """(text, images) - every image file named in text, in order, each once,
    as {"path", "mime", "data"} with data base64-encoded.

    In the returned text each path is replaced by "[Image #N]". Left in, the
    path reads as a second, separate thing next to the image, and a model
    with file tools goes off to open it instead of looking.
    """
    images = []
    numbers = {}    # path -> N, so a path named twice is one image
    spans = []      # (start, end, N)
    for match in EXTENSION.finditer(text):
        found = find_path(text, match.end())
        if not found:
            continue
        start, path = found
        path = os.path.realpath(path)
        mime, _ = mimetypes.guess_type(path)
        if mime not in IMAGE_TYPES:
            continue
        if path not in numbers:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            images.append({"path": path, "mime": mime, "data": data})
            numbers[path] = len(images)
        end = match.end()
        # the quotes around a path go with it
        if 0 < start and end < len(text) and text[start - 1] == text[end] and text[end] in "'\"":
            start, end = start - 1, end + 1
        spans.append((start, end, numbers[path]))

    for start, end, number in reversed(spans):
        text = text[:start] + f"[Image #{number}]" + text[end:]
    return text, images
