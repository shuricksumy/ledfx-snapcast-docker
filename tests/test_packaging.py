"""The image has to actually contain what the entrypoint imports."""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def dockerfile():
    with open(os.path.join(ROOT, "Dockerfile")) as handle:
        return handle.read()


def test_every_root_module_is_copied_into_the_image():
    """startup.py imports these; a module left out of COPY is a container that
    crash-loops on ImportError with a green build behind it."""
    copied = " ".join(re.findall(r"^COPY (.+)$", dockerfile(), re.M))
    for name in sorted(f for f in os.listdir(ROOT) if f.endswith(".py")):
        assert name in copied, "%s is not COPYed into the image" % name


def test_the_page_is_copied_too():
    assert re.search(r"^COPY static/", dockerfile(), re.M)


def test_the_entrypoint_uses_the_system_interpreter():
    """PATH puts the LedFx venv first, and that interpreter cannot see the
    apt-installed Flask in /usr/lib/python3/dist-packages - a bare `python3`
    entrypoint would fail to import the panel at boot."""
    assert '"/usr/bin/python3"' in dockerfile()


def test_flask_comes_from_apt_not_pip():
    body = dockerfile()
    assert "python3-flask" in body
    assert not re.search(r"pip install[^\n]*\bflask\b", body)


def test_the_panel_port_is_exposed():
    assert re.search(r"^EXPOSE 8080", dockerfile(), re.M)


def test_the_audio_path_still_carries_its_warnings():
    """Each of these lines exists because something broke without it; a future
    edit that drops the comment has probably dropped the reason too."""
    body = dockerfile()
    assert "autospawn = no" in body
    assert "PULSE_LATENCY_MSEC" in body
    assert "asound.conf" in body
