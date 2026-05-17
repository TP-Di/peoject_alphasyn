from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from main import main as send_birthdays


def job():
    print("Triggered daily_birthdays", flush=True)
    send_birthdays()


if __name__ == "__main__":
    scheduler = BlockingScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(
        job,
        CronTrigger(hour=9, minute=0),
        id="daily_birthdays",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    print("Scheduler started: daily_birthdays at 09:00 Asia/Tashkent", flush=True)
    scheduler.start()
