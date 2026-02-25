def build_bar(percentage: float, length: int = 10):
    filled = int(round((percentage / 100) * length))
    empty = length - filled
    return "▰" * filled + "▱" * empty


def calculate_percentages(vote_counts: dict):
    total = sum(vote_counts.values())
    if total == 0:
        return {k: 0 for k in vote_counts}, 0

    percentages = {
        k: round((v / total) * 100)
        for k, v in vote_counts.items()
    }

    return percentages, total


def format_time_remaining(seconds: int):
    if seconds <= 0:
        return "00:00"

    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02}:{secs:02}"
