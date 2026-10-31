from django.db import migrations


def copy_data(apps, schema_editor):
    """Übernimmt Locations (→ Venues), Artists und Upcoming Events aus der alten App events."""
    Location, OldArtist, OldEvent = (apps.get_model('events', m) for m in ('Location', 'Artist', 'UpcomingEvent'))
    Venue, Artist, UpcomingEvent = (apps.get_model('leisure', m) for m in ('Venue', 'Artist', 'UpcomingEvent'))
    venues = {
        old.pk: Venue.objects.get_or_create(name=old.name, defaults={
            'country': old.country, 'info': old.info, 'picture_url': old.picture_url, 'rating': old.rating})[0]
        for old in Location.objects.all()
    }
    artists = {
        old.pk: Artist.objects.get_or_create(name=old.name, defaults={
            'rating': old.rating, 'info': old.info, 'song_url': old.song_url})[0]
        for old in OldArtist.objects.all()
    }
    for old in OldEvent.objects.all():
        UpcomingEvent.objects.get_or_create(
            venue=venues[old.location_id], artist=artists[old.artist_id], date=old.date,
            defaults={'info': old.info, 'ticket_url': old.ticket_url})


class Migration(migrations.Migration):

    dependencies = [
        ('leisure', '0001_initial'),
        ('events', '0005_task_nach_tasks_app'),
    ]

    operations = [
        migrations.RunPython(copy_data, migrations.RunPython.noop),
    ]
