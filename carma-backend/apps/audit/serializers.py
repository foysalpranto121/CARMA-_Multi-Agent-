from rest_framework import serializers
from .models import AuditLogEntry


class AuditLogEntrySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model  = AuditLogEntry
        fields = '__all__'
        read_only_fields = ['id', 'sequence_num', 'prev_hash', 'entry_hash', 'timestamp']

    def get_actor_name(self, obj):
        if obj.actor_user:
            return obj.actor_user.get_full_name()
        return obj.actor_agent or 'system'
