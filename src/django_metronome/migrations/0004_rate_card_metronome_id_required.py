# Metronome assigns rate card IDs via v1.contracts.rate_cards.create; the Django
# mirror must not invent local IDs.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("django_metronome", "0003_rate_card_optional_metronome_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="metronomeratecard",
            name="metronome_id",
            field=models.CharField(db_index=True, max_length=255),
        ),
    ]
