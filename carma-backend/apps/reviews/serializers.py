from rest_framework import serializers
from .models import Escalation, HumanReview


class EscalationSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.SerializerMethodField()
    scenario_code    = serializers.SerializerMethodField()
    case_id          = serializers.SerializerMethodField()

    class Meta:
        model  = Escalation
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to else None

    def get_scenario_code(self, obj):
        try:
            return obj.adaptation.benchmark_case.scenario.code
        except Exception:
            return None

    def get_case_id(self, obj):
        try:
            return obj.adaptation.benchmark_case.case.case_id
        except Exception:
            return None


class HumanReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(source='reviewer.get_full_name', read_only=True)

    class Meta:
        model  = HumanReview
        fields = '__all__'
        read_only_fields = ['id', 'reviewer', 'reviewed_at']
