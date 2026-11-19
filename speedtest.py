#!/usr/bin/env python3

import argparse
import sys
import time
import urllib.error
import urllib.request

REQUESTS_COUNT = 10
CHUNK_SIZE = 64 * 1024
REQUEST_TIMEOUT = 60      # лимит на один запрос целиком, секунды
MIN_RELIABLE_TIME = 0.1   # меньше этого суммарного времени скорость считать нельзя
MIN_RELIABLE_BYTES = 100 * 1024

# Готовые адреса: python3 speedtest.py -s 10
PRESETS = {
    1: "https://speed.cloudflare.com/__down?bytes=1000000",
    5: "https://speed.cloudflare.com/__down?bytes=5000000",
    10: "https://speed.cloudflare.com/__down?bytes=10000000",
    25: "https://speed.cloudflare.com/__down?bytes=25000000",
    100: "https://nbg1-speed.hetzner.com/100MB.bin",
}
DEFAULT_SIZE = 10


def download(url: str, timeout: float, label: str = "") -> tuple[int, float]:

    req = urllib.request.Request(
        url, headers={"Cache-Control": "no-cache", "User-Agent": "speedtest/1.0"}
    )
    start = time.perf_counter()
    size = 0
    # timeout сокета ограничивает паузу между байтами, а общий лимит — ниже
    show = sys.stdout.isatty()
    last_shown = 0.0
    with urllib.request.urlopen(req, timeout=min(timeout, 30)) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        while chunk := resp.read(CHUNK_SIZE):
            size += len(chunk)
            now = time.perf_counter()
            if now - start > timeout:
                raise TimeoutError(f"запрос длится дольше {timeout:g} с")
            if show and now - last_shown >= 0.2:
                last_shown = now
                pct = f" ({size * 100 // total}%)" if total else ""
                print(f"\r{label}: скачано {format_size(size)}{pct}   ",
                      end="", flush=True)
    elapsed = time.perf_counter() - start
    if show:
        print("\r" + " " * 60 + "\r", end="", flush=True)  # стереть строку прогресса
    return size, elapsed


def format_speed(bits_per_sec: float) -> str:
    """Подбирает единицу, чтобы число было читаемым: бит/с ... Гбит/с."""
    for unit, factor in (("Гбит/с", 1e9), ("Мбит/с", 1e6), ("Кбит/с", 1e3)):
        if bits_per_sec >= factor:
            return f"{bits_per_sec / factor:.2f} {unit}"
    return f"{bits_per_sec:.0f} бит/с"


def format_size(num_bytes: int) -> str:
    for unit, factor in (("ГБ", 1e9), ("МБ", 1e6), ("КБ", 1e3)):
        if num_bytes >= factor:
            return f"{num_bytes / factor:.2f} {unit}"
    return f"{num_bytes} Б"


def main() -> int:
    parser = argparse.ArgumentParser(description="Замер скорости скачивания")
    parser.add_argument(
        "url", nargs="?",
        help="свой адрес для скачивания (если не указан — берётся готовый по --size)",
    )
    parser.add_argument(
        "-s", "--size", type=int, choices=sorted(PRESETS), default=DEFAULT_SIZE,
        help=f"готовый файл, МБ (по умолчанию {DEFAULT_SIZE})",
    )
    parser.add_argument(
        "-n", "--count", type=int, default=REQUESTS_COUNT,
        help=f"количество запросов (по умолчанию {REQUESTS_COUNT})",
    )
    parser.add_argument(
        "-t", "--timeout", type=float, default=REQUEST_TIMEOUT,
        help=f"лимит на один запрос, секунды (по умолчанию {REQUEST_TIMEOUT})",
    )
    parser.add_argument(
        "-d", "--delay", type=float, default=0,
        help="пауза между запросами, секунды (по умолчанию 0); в замер не входит",
    )
    args = parser.parse_args()
    if args.count < 1 or args.timeout <= 0 or args.delay < 0:
        parser.error("count и timeout должны быть положительными, delay — не меньше 0")

    url = args.url or PRESETS[args.size]
    print(f"Адрес: {url}")

    total_bytes = 0
    total_time = 0.0
    done = 0

    try:
        for i in range(1, args.count + 1):
            if i > 1 and args.delay:
                time.sleep(args.delay)
            label = f"Запрос {i}/{args.count}"
            try:
                size, elapsed = download(url, args.timeout, label)
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
                print(f"Запрос {i}/{args.count}: ошибка — {e}", file=sys.stderr)
                continue
            total_bytes += size
            total_time += elapsed
            done += 1
            print(f"Запрос {i}/{args.count}: {format_size(size)} за {elapsed:.3f} с")
    except KeyboardInterrupt:
        print("\nПрервано, показываю результат по выполненным запросам")

    if done == 0:
        print("Не удалось выполнить ни одного запроса", file=sys.stderr)
        return 1
    if total_bytes == 0:
        print("Сервер вернул пустой ответ, скорость посчитать нельзя", file=sys.stderr)
        return 1

    print("-" * 40)
    print(f"Успешных запросов:     {done} из {args.count}")
    print(f"Среднее время запроса: {total_time / done:.3f} с")
    print(f"Скачано всего:         {format_size(total_bytes)}")

    if total_time < MIN_RELIABLE_TIME or total_bytes < MIN_RELIABLE_BYTES:
        # слишком мало данных или времени: таймер неточен, цифра будет мусорной
        print(
            "Скорость: не определена — замер слишком короткий. "
            "Возьмите файл побольше или канал медленнее.",
            file=sys.stderr,
        )
        return 2

    bits_per_sec = total_bytes * 8 / total_time
    print(f"Скорость скачивания:   {format_speed(bits_per_sec)} "
          f"({format_size(int(bits_per_sec / 8))}/с)")
    if done < args.count:
        print(f"Внимание: {args.count - done} запрос(ов) не удались, "
              "результат посчитан по остальным.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
