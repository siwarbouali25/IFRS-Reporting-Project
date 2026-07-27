from rest_framework.permissions import BasePermission


ADMIN_ROLE = "admin"
AUDITOR_ROLE = "auditor"
EXPERT_REVIEWER_ROLE = "expert_reviewer"


class CanSubmitReportForReview(BasePermission):
    """
    Allow auditors to submit reports they created.

    Administrators may submit any report so they can recover exceptional
    workflows without weakening the normal creator ownership rule.
    """

    message = (
        "Only the report creator or an administrator can submit this report "
        "for review."
    )

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {ADMIN_ROLE, AUDITOR_ROLE}
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == ADMIN_ROLE:
            return True
        return obj.created_by_id == request.user.id


class CanReviewReport(BasePermission):
    """
    Allow expert reviewers and administrators to record review decisions.

    Expert reviewers cannot decide on a version they created. Administrators
    retain an explicit override for exceptional cases.
    """

    message = (
        "Only an independent expert reviewer or an administrator can review "
        "this report."
    )

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {ADMIN_ROLE, EXPERT_REVIEWER_ROLE}
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == ADMIN_ROLE:
            return True
        return obj.created_by_id != request.user.id
