/**
 * Show/hide the verification_schedule field based on verification_trigger value.
 * Schedule is only needed when trigger is "scheduled" or "both".
 */
(function () {
    "use strict";

    function toggleScheduleField() {
        var triggerField = document.getElementById("id_verification_trigger");
        var scheduleRow = document.getElementById("id_verification_schedule");
        if (!triggerField || !scheduleRow) {
            return;
        }
        var container = scheduleRow.closest(".form-group") || scheduleRow.parentElement;
        if (!container) {
            return;
        }
        var value = triggerField.value;
        if (value === "scheduled" || value === "both") {
            container.style.display = "";
        } else {
            container.style.display = "none";
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        toggleScheduleField();
        var triggerField = document.getElementById("id_verification_trigger");
        if (triggerField) {
            triggerField.addEventListener("change", toggleScheduleField);
        }
    });
})();
