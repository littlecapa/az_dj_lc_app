from django.core.management.base import BaseCommand
from homepage.models import BlogPost
import json

class Command(BaseCommand):
    help = 'Syncs BlogPost data from local to Azure (exports local, imports to Azure)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--export',
            action='store_true',
            help='Export local data to JSON file'
        )
        parser.add_argument(
            '--import',
            action='store_true',
            help='Import data from JSON file (clears existing data first)'
        )
        parser.add_argument(
            '--file',
            type=str,
            default='blogposts_backup.json',
            help='JSON file path (default: blogposts_backup.json)'
        )

    def handle(self, *args, **options):
        filename = options['file']

        if options['export']:
            self.export_data(filename)
        elif options['import']:
            self.import_data(filename)
        else:
            self.stdout.write(
                self.style.ERROR('Please specify --export or --import')
            )

    def export_data(self, filename):
        """Export all BlogPost data to JSON"""
        posts = BlogPost.objects.all().values(
            'date', 'headline', 'summary', 'image_name', 
            'external_url', 'slug', 'is_active'
        )
        data = list(posts)
        
        # Convert date objects to strings
        for post in data:
            post['date'] = str(post['date'])
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Exported {len(data)} posts to {filename}')
        )

    def import_data(self, filename):
        """Import BlogPost data from JSON (clears existing data first)"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'File {filename} not found!')
            )
            return

        # Delete all existing posts
        deleted_count = BlogPost.objects.all().count()
        BlogPost.objects.all().delete()
        self.stdout.write(
            self.style.WARNING(f'Deleted {deleted_count} existing posts')
        )

        # Create new posts
        created_count = 0
        for post_data in data:
            BlogPost.objects.create(**post_data)
            created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'✓ Created {created_count} new posts')
        )
