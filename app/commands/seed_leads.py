import asyncio

from sqlalchemy import select

from app.db.session import async_session
from app.modules.leads.models import Lead
from app.shared.enums import LeadStatus

SAMPLE_LEADS = [
    ("Aarav Mehta", "aarav.mehta@example.com", "919810000001", "Instagram", LeadStatus.NEW),
    ("Diya Sharma", "diya.sharma@example.com", "919810000002", "Website", LeadStatus.NEW),
    ("Kabir Singh", "kabir.singh@example.com", "919810000003", "Referral", LeadStatus.NEW),
    ("Ananya Iyer", "ananya.iyer@example.com", "919810000004", "Instagram", LeadStatus.NEW),
    ("Vivaan Kapoor", "vivaan.kapoor@example.com", "919810000005", "Google", LeadStatus.CONTACTED),
    ("Isha Nair", "isha.nair@example.com", "919810000006", "Website", LeadStatus.CONTACTED),
    (
        "Reyansh Gupta",
        "reyansh.gupta@example.com",
        "919810000007",
        "Referral",
        LeadStatus.CONTACTED,
    ),
    ("Myra Joshi", "myra.joshi@example.com", "919810000008", "Instagram", LeadStatus.CONTACTED),
    ("Arjun Rao", "arjun.rao@example.com", "919810000009", "Google", LeadStatus.TRIAL_BOOKED),
    (
        "Saanvi Patel",
        "saanvi.patel@example.com",
        "919810000010",
        "Website",
        LeadStatus.TRIAL_BOOKED,
    ),
    (
        "Advait Verma",
        "advait.verma@example.com",
        "919810000011",
        "Referral",
        LeadStatus.TRIAL_BOOKED,
    ),
    (
        "Kiara Malhotra",
        "kiara.malhotra@example.com",
        "919810000012",
        "Instagram",
        LeadStatus.TRIAL_BOOKED,
    ),
    ("Rohan Das", "rohan.das@example.com", "919810000013", "Google", LeadStatus.ENROLLED),
    ("Aanya Bhat", "aanya.bhat@example.com", "919810000014", "Website", LeadStatus.ENROLLED),
    ("Ishaan Khanna", "ishaan.khanna@example.com", "919810000015", "Referral", LeadStatus.ENROLLED),
    (
        "Meera Kulkarni",
        "meera.kulkarni@example.com",
        "919810000016",
        "Instagram",
        LeadStatus.ENROLLED,
    ),
    ("Neil Fernandes", "neil.fernandes@example.com", "919810000017", "Google", LeadStatus.LOST),
    ("Tara Menon", "tara.menon@example.com", "919810000018", "Website", LeadStatus.LOST),
    ("Vihaan Sethi", "vihaan.sethi@example.com", "919810000019", "Referral", LeadStatus.LOST),
    ("Nisha Chawla", "nisha.chawla@example.com", "919810000020", "Instagram", LeadStatus.LOST),
]


async def run() -> tuple[int, int]:
    async with async_session() as session:
        emails = [lead[1] for lead in SAMPLE_LEADS]
        existing_emails = set(
            await session.scalars(select(Lead.email).where(Lead.email.in_(emails)))
        )
        created = 0
        for full_name, email, phone, source, status in SAMPLE_LEADS:
            if email in existing_emails:
                continue
            session.add(
                Lead(
                    full_name=full_name,
                    email=email,
                    phone=phone,
                    source=source,
                    status=status,
                )
            )
            created += 1
        await session.commit()
    return created, len(SAMPLE_LEADS) - created


def main() -> None:
    created, skipped = asyncio.run(run())
    print(f"Lead seed complete: created={created}, skipped={skipped}")


if __name__ == "__main__":
    main()
