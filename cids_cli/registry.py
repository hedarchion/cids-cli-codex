"""Registry of browser-observed CIDS functions.

The application is a server-rendered PHP site, not a public REST API. Each
entry mirrors an authenticated route or form target. Unverified submissions
are identified in notes and guarded as mutations.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class FunctionSpec:
    name: str
    method: str
    path: str
    description: str
    params: Tuple[str, ...] = ()
    mutating: bool = False
    aliases: Tuple[str, ...] = ()
    notes: str = ""
    json_body: bool = False

    @property
    def placeholders(self) -> Tuple[str, ...]:
        found: List[str] = []
        start = 0
        while True:
            left = self.path.find("{", start)
            if left < 0:
                break
            right = self.path.find("}", left + 1)
            if right < 0:
                break
            key = self.path[left + 1:right]
            if key and key not in found:
                found.append(key)
            start = right + 1
        return tuple(found)


F = FunctionSpec
FORM = "Form-dependent fields: inspect the live form and use dry-run first."

FUNCTIONS: Tuple[FunctionSpec, ...] = (
    # Top-level navigation.
    F("home", "GET", "main.php", "Authenticated CIDS home"),
    F("lesson-planning.home", "GET", "main9.php", "Lesson planning (DLP) home"),
    F("cocurricular.home", "GET", "koku.php", "Co-curricular home"),
    F("lesson-study.home", "GET", "formsLS.php", "Lesson Study home"),
    F("skas.home", "GET", "formsSKPM.php", "SKPM Kualiti@Sekolah home"),

    # Lesson planning, records, MIW and RPH/DLP.
    F("records.new-form", "GET", "record.php?action=newmiw", "Create-record form"),
    F("records.create", "POST", "set9.php", "Create a lesson-planning record", mutating=True, notes=FORM),
    F("records.list", "GET", "search9.php?action=listmiw", "List lesson-planning records", ("cgcl", "sgs", "l", "ml", "yl")),
    F("records.archive", "GET", "search9.php?action=listarchive", "List archived records"),
    F("records.shared", "GET", "search9.php?action=sharedmiw", "List shared records"),
    F("reference.list", "GET", "search9.php?action=searchlib", "Search reference designs", ("cg", "cl", "sg", "s", "page", "l")),
    F("reference.copy", "GET", "record.php?action=copymiw&id={id}", "Copy a reference design", ("id",), True, notes="Side-effecting legacy link."),
    F("miw.open", "GET", "miw9.php?action=openmiw&id={id}", "Open a MIW record", ("id",), aliases=("open-miw",)),
    F("miw.open-shared", "GET", "miw9.php?action=openmiw&op=shared&id={id}", "Open a shared MIW record", ("id",)),
    F("miw.edit", "POST", "record.php?action=editmiw", "Edit a MIW record", ("id",), True, notes=FORM),
    F("miw.delete", "POST", "record.php?action=deletemiw", "Delete a MIW record", ("id",), True, notes=FORM),
    F("miw.clear", "POST", "main9.php?action=clearmiw", "Clear MIW state", mutating=True, notes="Potentially destructive; form-dependent scope."),
    F("lesson.open", "GET", "miw9.php?action=openRPH&rph={rph}", "Open an RPH/DLP", ("rph",), aliases=("open-rph",)),
    F("lesson.submit-action", "POST", "miw9.php", "Run a DLP action", mutating=True, notes="Edit/link/SK@S/delete actions require a fresh randomtoken and form context."),
    F("lesson.upload", "POST", "upload.php?action=uploadRPH", "Upload an RPH attachment", mutating=True, notes=FORM),
    F("reflection.upload", "POST", "upload.php?action=uploadRefleksi", "Upload a reflection", mutating=True, notes=FORM),
    F("lesson.print", "GET", "printRPH.php?rphFormat={rph_format}", "Render an RPH for printing", ("rph_format",)),
    F("lesson.print-pdf", "GET", "printRPH.php?out=pdf&rphFormat={rph_format}", "Render an RPH as PDF", ("rph_format",)),
    F("miw.print-pdf", "GET", "print.php?as=pdf", "Render the current MIW as PDF"),

    # Yearly instructional plans.
    F("yip.list", "GET", "record.php?action=search_yearly", "List yearly instructional plans", ("cg", "cl", "sg", "s", "tahun")),
    F("yip.shared", "GET", "record.php?action=sharedrpt", "List shared yearly plans"),
    F("yip.open", "GET", "rpt9.php?action=create_rpt&id={id}&cg={cg}&cl={cl}&s={s}&tahun={year}&user={user}", "Open a YIP editor/view", ("id", "cg", "cl", "s", "year", "user")),
    F("yip.save", "POST", "rpt9.php", "Save YIP content", mutating=True, notes=FORM),
    F("yip.create", "POST", "rpt9.php?action=createRPT", "Create a YIP/RPT", mutating=True, notes=FORM),
    F("yip.copy", "GET", "record.php?action=copyrpt&id={id}&user={user}&src=", "Copy a YIP", ("id", "user"), True, notes="Side-effecting legacy link."),
    F("yip.delete", "GET", "record.php?action=delete_rpt&id={id}&user={user}&src=", "Delete a YIP", ("id", "user"), True, notes="Destructive legacy GET."),
    F("yip.share", "GET", "record.php?action=sharerpt&id={id}&user={user}&src=", "Share a YIP", ("id", "user"), True, notes="Side-effecting legacy link."),

    # Classes, timetable and planning settings.
    F("classes.new-form", "GET", "set9.php?action=LeaCla&do=createcombined", "Combined-class creation form"),
    F("classes.list", "GET", "set9.php?action=LeaCla&do=search", "List/edit combined classes"),
    F("classes.save", "POST", "set9.php", "Create or update a combined class", mutating=True, notes=FORM),
    F("timetable.form", "GET", "teachers9.php?action=waktumengajar", "Instructional timetable form"),
    F("timetable.view", "GET", "teachers9.php?action=viewjadual&user={user}", "View a teacher timetable", ("user",)),
    F("timetable.calendar", "GET", "teachers9.php?action=calendar", "View the academic calendar"),
    F("timetable.review", "GET", "teachers9.php?action=semakjadual&setjadual={id}", "Review a timetable", ("id",)),
    F("timetable.save", "POST", "teachers9.php", "Save timetable settings", mutating=True, notes=FORM),
    F("timetable.activate", "POST", "teachers9.php?action=aktifjadual", "Activate a timetable", mutating=True, notes=FORM),
    F("timetable.delete", "POST", "teachers9.php?action=deletejadual", "Delete a timetable", ("id",), True, notes=FORM),
    F("settings.instructional-profile", "GET", "set9.php?action=InsPro", "Instructional-profile settings"),
    F("settings.instructional-events", "GET", "set9.php?action=FacPro", "Instructional-event settings"),
    F("settings.save", "POST", "set9.php", "Save planning settings", mutating=True, notes=FORM),
    F("settings.competencies-info", "GET", "set9.php?action=kompetensi", "Competency information"),
    F("settings.instructional-info", "GET", "set9.php?action=instructional", "Knowledge/instructional information"),
    F("settings.learning-profile-info", "GET", "set9.php?action=learningprofile", "Learner-profile information"),
    F("settings.building-character", "GET", "set9.php?action=buildingcharacter", "Character selections"),
    F("settings.developing-skills", "GET", "set9.php?action=developingskills", "Skills selections"),
    F("settings.meta-learning", "GET", "set9.php?action=instillingmetalearning", "Meta-learning selections"),
    F("settings.media", "GET", "set9.php?action=media9", "Learner/media selections"),
    F("settings.modular", "GET", "set9.php?action=modular", "Modular settings", notes="Script-observed; schema unverified."),
    F("settings.reset", "POST", "set9.php?action=resetsetting", "Reset planning settings", mutating=True, notes="Destructive; form-dependent scope."),

    # Co-curricular functions.
    F("cocurricular.new-form", "GET", "koku.php?action=start", "New co-curricular plan form"),
    F("cocurricular.save", "POST", "koku.php", "Create or update a co-curricular plan", mutating=True, notes=FORM),
    F("cocurricular.list", "GET", "koku.php?action=list", "List co-curricular plans", ("jp", "np", "ml", "yl")),
    F("cocurricular.students-upload-form", "GET", "kokuAddUser.php", "Student-list upload form"),
    F("cocurricular.students-upload", "POST", "kokuAddUser.php", "Upload an XLSX student list", mutating=True, notes=FORM),
    F("cocurricular.students-assign-form", "GET", "kokuAddUser.php?action=assignstudent", "Student assignment form"),
    F("cocurricular.students-assign", "GET", "kokuAddUser.php?action=assignstudent", "Assign students to an activity", ("jenis_program", "nama_program", "do"), True, notes="Legacy GET form may mutate; dry-run first."),
    F("cocurricular.weekly-attendance", "GET", "kokuAddUser.php?action=weeklyattendance", "Weekly attendance report"),
    F("cocurricular.attendance-save", "POST", "kokuAddUser.php?action=attendance", "Record attendance", mutating=True, notes=FORM),
    F("cocurricular.analysis", "GET", "koku.php?action=analysis", "Overall attendance analysis"),

    # Lesson Study and SK@S.
    F("lesson-study.search", "GET", "formsLS.php?action=searchmiw&sop=lessonstudy", "Search records for Lesson Study", ("cgcl", "sgs", "l", "ml", "yl")),
    F("lesson-study.list", "GET", "formsLS.php?action=list", "List Lesson Studies", ("gp", "ml", "yl")),
    F("lesson-study.submit", "POST", "formsLS.php", "Create or update a Lesson Study", mutating=True, notes=FORM),
    F("skas.search", "GET", "formsSKPM.php?action=searchmiw&sop=skpmg2", "Search records for SK@S", ("cgcl", "sgs", "l", "ml", "yl")),
    F("skas.list", "GET", "formsSKPM.php?action=list_SKPM", "List SK@S evaluations", ("gp", "sesi")),
    F("skas.form", "GET", "formsSKPM.php?action=skpm&rph={rph}", "Open an SK@S evaluation form", ("rph",)),
    F("skas.submit", "POST", "formsSKPM.php", "Create or update an SK@S evaluation", mutating=True, notes=FORM),

    # Dashboard, profiles, resources, meetings and account.
    F("dashboard", "GET", "dashboard.php", "Statistics dashboard"),
    F("dashboard.detail", "GET", "dashboard.php?action=detail&id={id}", "List unsubmitted DLP", ("id",)),
    F("dashboard.required-hours", "GET", "dashboard.php?action=detailmmi&id={id}", "Analyze required subject hours", ("id",)),
    F("dashboard.submitted", "GET", "dashboard.php?action=submitteddetail&id={id}", "List submitted DLP", ("id",)),
    F("dashboard.full", "GET", "dashboard.php?action=fulldetail&id={id}", "All required DLP status", ("id",)),
    F("dashboard.manual", "GET", "dashboard.php?action=submittedmanual&id={id}", "List manually submitted DLP", ("id",)),
    F("profile.form", "GET", "admin9.php?action=profail", "User profile form"),
    F("profile.save", "POST", "admin9.php", "Save user profile", mutating=True, notes=FORM),
    F("institution.form", "GET", "admin9.php?action=profail_institusi", "Institution profile"),
    F("institution.save", "POST", "admin9.php", "Save institution profile", mutating=True, notes=FORM),
    F("resources.list", "GET", "resource.php", "List library resources"),
    F("resource.view", "GET", "resource.php?action=view&id={id}", "View a library resource", ("id",)),
    F("media.gallery", "GET", "mediagallery.php?pop=1", "Open the media gallery"),
    F("meeting.form", "GET", "meeting9.php?action=videomeet", "VideoCorps meeting form"),
    F("meeting.create", "POST", "meeting9.php", "Create a private meeting", ("roomname", "action", "do"), True, notes=FORM),
    F("meeting.delete", "POST", "meeting9.php", "Delete a private meeting", ("roomid", "action", "do"), True, notes=FORM),
    F("account.status", "GET", "akaun.php", "Account/subscription status"),
    F("account.subscribe", "GET", "akaun.php?action=upgrade", "Subscription options"),
    F("account.add-users", "GET", "akaun.php?action=update", "Add-user-quantity options"),
    F("account.user-admin", "GET", "akaun.php?action=useradmin", "License assignment"),
    F("account.payment-history", "GET", "akaun.php?action=history", "Payment history"),
    F("account.coupon", "POST", "akaun.php", "Apply an activation coupon", ("couponcode",), True, notes="May alter account state."),

    # Script-observed helpers. No unrestricted raw-request command is exposed.
    F("internal.keepalive", "GET", "fetch_data.php", "Refresh the session", notes="Observed in a 10-minute page timer."),
    F("internal.options", "POST", "fetch_data.php", "Resolve dependent form options", ("get_key", "get_option", "get_selected", "get_parent", "get_keepold", "get_group"), notes="Read-only POST used by the site's dependent selects."),
    F("internal.timetable-options", "POST", "teachers9.php", "Resolve timetable slots for a lesson", ("action", "option", "setjadual", "gls", "slot"), notes="Read-only AJAX request; use action=semakjadual and option=ajax."),
    F("internal.slot-status", "POST", "fetch_userrequirement.php", "Check whether a lesson slot is available", ("get_option", "rphdate", "user_id", "sesi", "subject", "learners", "time_from", "time_to"), notes="Read-only preflight used before Create DLP."),
    F("internal.miw-week", "POST", "fetch_json.php", "Resolve a date to an instructional week", ("action", "get_selected"), notes="Use action=miwweek."),
    F("internal.questions", "GET", "fetch_questions.php", "Fetch question data", notes="Parameters unverified."),
    F("internal.settings", "GET", "fetch_setting.php", "Fetch setting data", notes="Parameters unverified."),
    F("internal.lessons", "GET", "get_lessons.php", "Fetch lesson data", notes="Parameters unverified."),
    F("internal.user-phone", "GET", "fetch_user_phone.php?user_id={user_id}", "Fetch a user phone value", ("user_id",), notes="Returns sensitive contact data."),
    F("smart-search", "POST", "fetch_smartsearch.php", "Run AI-assisted Smart Search", ("id", "category", "selected"), True, notes="JSON response selectedOptions; may consume service quota.", json_body=True),
    F("chat", "POST", "chat.php", "Use the chat assistant", mutating=True, notes="Payload unverified; direct browser inspection was blocked."),
)


def _index() -> Dict[str, FunctionSpec]:
    result: Dict[str, FunctionSpec] = {}
    for spec in FUNCTIONS:
        result[spec.name] = spec
        for alias in spec.aliases:
            result[alias] = spec
    return result


REGISTRY = _index()


def get_function(name: str) -> Optional[FunctionSpec]:
    return REGISTRY.get(name)


def iter_functions() -> Iterable[FunctionSpec]:
    return FUNCTIONS


def as_dict(spec: FunctionSpec) -> Mapping[str, object]:
    return {
        "name": spec.name, "method": spec.method, "path": spec.path,
        "description": spec.description, "params": list(spec.params),
        "mutating": spec.mutating, "aliases": list(spec.aliases),
        "notes": spec.notes, "json_body": spec.json_body,
    }
