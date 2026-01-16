import random
from dataclasses import dataclass
from typing import List


@dataclass
class Grain:
    x: float
    y: float
    vx: float


@dataclass
class Sparkle:
    x: int
    y: int
    ttl: float


class SandColumn:
    def __init__(self) -> None:
        self.grains: List[Grain] = []
        self.sparkles: List[Sparkle] = []
        self.spawn_accum = 0.0
        self.fall_speed = 6.0

    def reset(self) -> None:
        self.grains.clear()
        self.sparkles.clear()
        self.spawn_accum = 0.0

    def update(self, dt: float, inner_left: int, inner_right: int, inner_top: int, surface_row: int, paused: bool) -> None:
        if paused:
            return
        if inner_left > inner_right:
            return

        self.spawn_accum += dt
        while self.spawn_accum >= 1.0:
            self.spawn_accum -= 1.0
            start_x = (inner_left + inner_right) / 2.0 + random.uniform(-1.0, 1.0)
            start_x = max(inner_left, min(inner_right, start_x))
            self.grains.append(Grain(x=start_x, y=inner_top, vx=random.uniform(-0.4, 0.4)))

        for grain in list(self.grains):
            grain.vx += random.uniform(-0.6, 0.6) * dt
            grain.vx = max(-0.6, min(0.6, grain.vx))
            next_x = grain.x + grain.vx
            if next_x < inner_left and grain.vx < 0:
                grain.vx = -grain.vx
                next_x = inner_left + 1
            elif next_x > inner_right and grain.vx > 0:
                grain.vx = -grain.vx
                next_x = inner_right - 1

            grain.x = max(inner_left, min(inner_right, next_x))
            grain.y += self.fall_speed * dt

            if grain.y >= surface_row - 1:
                self.grains.remove(grain)
                sparkle_ttl = random.uniform(0.5, 1.5)
                sparkle_y = max(inner_top, surface_row - 1)
                self.sparkles.append(Sparkle(x=int(round(grain.x)), y=sparkle_y, ttl=sparkle_ttl))

        for sparkle in list(self.sparkles):
            sparkle.ttl -= dt
            if sparkle.ttl <= 0:
                self.sparkles.remove(sparkle)

    def render(self, canvas, grain_ch: str = ".", sparkle_ch: str = "*") -> None:
        for grain in self.grains:
            x = int(round(grain.x))
            y = int(round(grain.y))
            if 0 <= y < len(canvas) and 0 <= x < len(canvas[0]):
                canvas[y][x] = grain_ch
        for sparkle in self.sparkles:
            if 0 <= sparkle.y < len(canvas) and 0 <= sparkle.x < len(canvas[0]):
                canvas[sparkle.y][sparkle.x] = sparkle_ch
