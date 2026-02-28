from models import init_db, SessionLocal, Account
import json

def seed_accounts():
    db = SessionLocal()
    
    # Check if we already have accounts
    if db.query(Account).count() > 0:
        print("Accounts already exist. Skipping seed.")
        db.close()
        return

    accounts_data = [
        {
            "name": "dominatusmetas_",
            "niche": "Mentalidad y Éxito Masculino",
            "keywords": ["mentalidad millonaria", "hábitos de éxito", "disciplina masculina", "finanzas personales"],
            "target_url": "https://link-to-hotmart.com/dominatus"
        },
        {
            "name": "reinventatemujer_",
            "niche": "Empoderamiento y Amor Propio Femenino",
            "keywords": ["empoderamiento femenino", "amor propio mujer", "glow up mental", "autodisciplina"],
            "target_url": "https://link-to-hotmart.com/reinventa"
        },
        {
            "name": "melchor_ia",
            "niche": "IA y Futuro",
            "keywords": ["herramientas IA gratis", "ganar dinero con IA", "noticias IA 2026", "automatización"],
            "target_url": "https://link-to-hotmart.com/melchor-ia"
        },
        {
            "name": "reglas.del.amor",
            "niche": "Relaciones y Psicología Masc.",
            "keywords": ["psicología masculina relaciones", "atraer a un hombre", "señales de interés hombres"],
            "target_url": "https://link-to-hotmart.com/reglas-amor"
        },
        {
            "name": "the_manifest_path",
            "niche": "Manifestación y Espiritualidad",
            "keywords": ["manifestation techniques", "law of attraction tips", "numerology secret codes"],
            "target_url": "https://link-to-hotmart.com/manifest"
        }
    ]

    for data in accounts_data:
        acc = Account(
            name=data["name"],
            niche=data["niche"],
            keywords=data["keywords"],
            target_url=data["target_url"]
        )
        db.add(acc)
    
    db.commit()
    print(f"Successfully seeded {len(accounts_data)} accounts.")
    db.close()

if __name__ == "__main__":
    init_db()
    seed_accounts()
