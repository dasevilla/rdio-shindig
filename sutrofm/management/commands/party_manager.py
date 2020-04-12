import logging
import time
import traceback
import uuid
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils.timezone import now

from sutrofm.models import Party, UserPartyPresence

logger = logging.getLogger(__name__)

USER_CHECK_IN_FREQUENCY = timedelta(minutes=1)
WAIT_FOR_USERS = timedelta(minutes=5)
TICK_FREQUENCY = 1  # seconds


class Command(BaseCommand):
  def add_arguments(self, parser):
    parser.add_argument('party_id', type=str)

  def __init__(self, *args, **kwargs):
    super(Command, self).__init__(*args, **kwargs)
    self.redis = None
    self.party = None
    self.party_id = None
    self.manager_uuid = None
    self.keep_running = True

  def handle(self, party_id, *args, **kwargs):
    self.manager_uuid = uuid.uuid4()
    self.party_id = party_id
    self.party = Party.objects.get(id=party_id)

    if self.party.needs_new_manager():
      logger.info(f'Starting up party manager {self.manager_uuid} for party {self.party_id}!')
      self.update_party_manager_timestamp()  # claim party immediately to avoid race conditions
    else:
      logger.info(f'Killing manager {self.manager_uuid}, party {self.party_id} already has an active manager')
      self.keep_running = False

    self.run()

  def run(self):
    while self.keep_running:
      try:
        self.maintain_party()
        self.keep_running = self.should_keep_running()
      except Exception as ex:
        print(ex)
        print(traceback.format_exc())
        logger.exception("!!! ALERT !!! Room manager... More like room blam-ager.")
      time.sleep(TICK_FREQUENCY)
    else:
      logger.info(f"Killing party manager {self.manager_uuid}, party {self.party_id} doesn't need it")

  def maintain_party(self):
    # Only load party data at beginning and save at end to reduce db calls
    self.party.refresh_from_db()

    self.update_track()
    self.prune_users()
    self.update_party_manager_timestamp()

    self.party.save()

  def should_keep_running(self):
    return self.party.user_count() and not self.other_manager_owns_party()

  def update_track(self):
    queue_size = self.party.queue.count()

    if not self.party.playing_item and not queue_size:
      logger.info('No tracks queued, nothing to do')
      return

    if not self.party.playing_item and queue_size:
      logger.info('No currently playing track, playing next in queue')
      self.party.play_next_queue_item()

    position_ms, duration_ms = self.party.playing_item.get_track_position()
    # TODO: broadcast track position update
    logger.info(
      f'Track position {round(position_ms)}ms of {duration_ms}ms total ({round(position_ms/duration_ms*100)}%)')

    if position_ms == duration_ms or self.party.playing_item.should_skip():
      self.party.play_next_queue_item()

  def prune_users(self):
    num_deleted, _ = UserPartyPresence.objects.filter(party=self.party, last_check_in__lt=now() - USER_CHECK_IN_FREQUENCY).delete()
    if num_deleted:
      logger.info(f'Pruned {num_deleted} user entries on party {self.party_id}')

  def update_party_manager_timestamp(self):
    logger.info(f'Updating party manager timestamp for {self.manager_uuid} on party {self.party_id}')
    self.party.last_manager_uuid = self.manager_uuid
    self.party.last_manager_check_in = now()

  def other_manager_owns_party(self):
    return self.manager_uuid != self.party.last_manager_uuid