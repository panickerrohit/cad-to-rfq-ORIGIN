"""Writes fake view PDFs (front/top/right/iso of an L-bracket) into fixtures/views/.

Stand-ins until Person 1's extract() produces real CadQuery views.
Run from api/:  python fixtures/make_fixture_views.py
"""
import os

from reportlab.pdfgen import canvas

OUT = os.path.join(os.path.dirname(__file__), "views")
S = 3.0  # pt per mm
W, D, H, T = 80, 60, 68, 8


def page(name, w, h, draw):
    c = canvas.Canvas(os.path.join(OUT, f"{name}.pdf"), pagesize=(w * S + 40, h * S + 40))
    c.translate(20, 20); c.setLineWidth(1.2)
    draw(c)
    c.save()


def front(c):
    c.rect(0, 0, W * S, H * S)
    c.setDash(4, 3); c.line(0, T * S, W * S, T * S); c.setDash()
    c.circle(40 * S, 38 * S, 11 * S)
    for dx in (-15.5, 15.5):
        for dz in (-15.5, 15.5):
            c.circle((40 + dx) * S, (38 + dz) * S, 1.65 * S)


def top(c):
    c.rect(0, 0, W * S, D * S)
    c.line(0, (D - T) * S, W * S, (D - T) * S)
    for hx in (12, 68):
        for hy in (18, 44):
            c.circle(hx * S, (D - hy) * S, 3.3 * S)


def right(c):
    p = c.beginPath()
    p.moveTo(0, 0); p.lineTo(D * S, 0); p.lineTo(D * S, T * S); p.lineTo(T * S, T * S)
    p.lineTo(T * S, H * S); p.lineTo(0, H * S); p.close()
    c.drawPath(p)


def iso(c):
    import math
    cx, cy = math.cos(math.radians(30)), math.sin(math.radians(30))

    def pt(x, y, z):
        return ((x - y) * cx * S * 0.8 + D * cx * S * 0.8, ((x + y) * cy + z) * S * 0.8)

    def poly(pts):
        p = c.beginPath(); p.moveTo(*pt(*pts[0]))
        for q in pts[1:]:
            p.lineTo(*pt(*q))
        p.close(); c.drawPath(p)

    poly([(0, 0, T), (W, 0, T), (W, D, T), (0, D, T)])          # base top
    poly([(0, 0, 0), (W, 0, 0), (W, 0, T), (0, 0, T)])          # base front
    poly([(0, D - T, T), (W, D - T, T), (W, D - T, H), (0, D - T, H)])  # upright face
    poly([(0, D - T, H), (W, D - T, H), (W, D, H), (0, D, H)])  # upright top


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    page("front", W, H, front)
    page("top", W, D, top)
    page("right", D, H, right)
    page("iso", W + D, H + 30, iso)
    print(OUT)
