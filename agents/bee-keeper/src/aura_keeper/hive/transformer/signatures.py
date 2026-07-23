import dspy


class DiagnoseError(dspy.Signature):
    """
    Analyze Hive system errors and provide diagnosis and fix suggestions.
    The BeeKeeper uses its wisdom to heal the Hive.
    """

    error_log = dspy.InputField(desc="Raw logs or error messages from the Hive.")
    system_context = dspy.InputField(
        desc="Current system vitals, metrics, and pod status."
    )

    diagnosis = dspy.OutputField(
        desc="A concise explanation of why the failure occurred."
    )
    fix_suggestion = dspy.OutputField(desc="A concrete step to resolve the issue.")
