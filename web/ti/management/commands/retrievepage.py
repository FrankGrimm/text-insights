from django.core.management.base import BaseCommand, CommandError

class RetrievePageCommand(BaseCommand):
    args = '<page_id> <oauth_token>'
    help = 'Retrieves data for the given fb page'

    def handle(self, *args, **options):
        if args is None or len(args) < 2:
            raise CommandError('Invalid arguments')

        self.stdout.write('RetrievePageCommand called with arguments %s' % args)
