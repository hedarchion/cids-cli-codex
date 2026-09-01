# Authenticated CIDS function map

This inventory was produced from authenticated, read-only browser exploration of
`https://asiemodel.net/model/` on 2026-09-01. Routes and forms were inspected, but
no create, edit, upload, meeting, account, payment, attendance, AI, share, copy, or
delete action was submitted.

Legend: **R** read-only, **W** create/update/upload/quota-impacting, **D** destructive
or sharing/copying. W/D functions require `--yes`; every function supports
`--dry-run`. “Form-dependent” means hidden fields or a current token must be read
from the live page before submission.

The registry in `cids_cli/registry.py` is the machine-readable source of truth.

## Navigation, profiles, resources, meetings and account

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `home` | GET `main.php` | R | Application home |
| `lesson-planning.home` | GET `main9.php` | R | DLP home |
| `cocurricular.home` | GET `koku.php` | R | Co-curricular home |
| `lesson-study.home` | GET `formsLS.php` | R | Lesson Study home |
| `skas.home` | GET `formsSKPM.php` | R | SKPM Kualiti@Sekolah home |
| `profile.form` | GET `admin9.php?action=profail` | R | User profile fields |
| `profile.save` | POST `admin9.php` | W | Profile fields, photo, signature, policy flags; form-dependent |
| `institution.form` | GET `admin9.php?action=profail_institusi` | R | Institution profile |
| `institution.save` | POST `admin9.php` | W | Institution form; form-dependent |
| `resources.list` | GET `resource.php` | R | Library list |
| `resource.view` | GET `resource.php?action=view&id={id}` | R | Resource detail/attachment |
| `media.gallery` | GET `mediagallery.php?pop=1` | R | Local media gallery |
| `meeting.form` | GET `meeting9.php?action=videomeet` | R | Public/private VideoCorps meetings |
| `meeting.create` | POST `meeting9.php` | W | `roomname`, `action`, `do` |
| `meeting.delete` | POST `meeting9.php` | D | `roomid`, `action`, `do` |
| `account.status` | GET `akaun.php` | R | Subscription/account status |
| `account.subscribe` | GET `akaun.php?action=upgrade` | R | Subscription options only |
| `account.add-users` | GET `akaun.php?action=update` | R | Add-user-quantity options only |
| `account.user-admin` | GET `akaun.php?action=useradmin` | R | License assignment UI |
| `account.payment-history` | GET `akaun.php?action=history` | R | Payment history |
| `account.coupon` | POST `akaun.php` | W | `couponcode`; changes account state |

Authentication is implemented separately: POST `index.php` with `username`,
`password`, and `submit`; session check uses GET `main.php`; logout uses GET
`logout.php?redirect=`.

## Lesson planning, MIW and DLP/RPH

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `records.new-form` | GET `record.php?action=newmiw` | R | New-record form |
| `records.create` | POST `set9.php` | W | name, class/subject, session, dates, weeks, action; form-dependent |
| `records.list` | GET `search9.php?action=listmiw` | R | `cgcl`, `sgs`, `l`, month/year filters |
| `records.archive` | GET `search9.php?action=listarchive` | R | Archived records |
| `records.shared` | GET `search9.php?action=sharedmiw` | R | Shared records |
| `reference.list` | GET `search9.php?action=searchlib` | R | class/subject/page filters |
| `reference.copy` | GET `record.php?action=copymiw&id={id}` | D | Side-effecting legacy copy link |
| `miw.open` | GET `miw9.php?action=openmiw&id={id}` | R | MIW detail |
| `miw.open-shared` | GET `miw9.php?action=openmiw&op=shared&id={id}` | R | Shared MIW detail |
| `miw.edit` | POST `record.php?action=editmiw` | W | MIW form/token; form-dependent |
| `miw.delete` | POST `record.php?action=deletemiw` | D | MIW id/token; form-dependent |
| `miw.clear` | POST `main9.php?action=clearmiw` | D | Scope unverified |
| `lesson.open` | GET `miw9.php?action=openRPH&rph={rph}` | R | DLP/RPH detail |
| `lesson.submit-action` | POST `miw9.php` | W/D | Edit, shared resources, SK@S, delete; requires `randomtoken` and current form context |
| `lesson.upload` | POST `upload.php?action=uploadRPH` | W | RPH file and metadata; form-dependent |
| `reflection.upload` | POST `upload.php?action=uploadRefleksi` | W | Reflection file and metadata; form-dependent |
| `lesson.print` | GET `printRPH.php?rphFormat={rph_format}` | R | Printable RPH |
| `lesson.print-pdf` | GET `printRPH.php?out=pdf&rphFormat={rph_format}` | R | RPH PDF |
| `miw.print-pdf` | GET `print.php?as=pdf` | R | MIW PDF |

The DLP form exposed fields including `class_id`, `submit_observe`, `src`,
`btnsubmit`, `action`, `randomtoken`, `id`, `owner_id`, `grouplevelsubject`,
`date`, and `dbug`. Button labels included Edit DLP, Delete DLP, Link to Shared
Resources, Print/Save PDF, Go to YIP Main Page, and SK@S.

## Yearly Instructional Plan (YIP)

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `yip.list` | GET `record.php?action=search_yearly` | R | `cg`, `cl`, `sg`, `s`, `tahun` |
| `yip.shared` | GET `record.php?action=sharedrpt` | R | Shared plans |
| `yip.open` | GET `rpt9.php?action=create_rpt&id={id}&cg={cg}&cl={cl}&s={s}&tahun={year}&user={user}` | R | Existing YIP editor/view |
| `yip.save` | POST `rpt9.php` | W | YIP content, dates/weeks, remarks; form-dependent |
| `yip.create` | POST `rpt9.php?action=createRPT` | W | Script-observed creation action |
| `yip.copy` | GET `record.php?action=copyrpt&id={id}&user={user}&src=` | D | Side-effecting legacy link |
| `yip.delete` | GET `record.php?action=delete_rpt&id={id}&user={user}&src=` | D | Destructive legacy GET |
| `yip.share` | GET `record.php?action=sharerpt&id={id}&user={user}&src=` | D | Side-effecting legacy link |

## Classes, timetable and planning settings

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `classes.new-form` | GET `set9.php?action=LeaCla&do=createcombined` | R | Combined-class form |
| `classes.list` | GET `set9.php?action=LeaCla&do=search` | R | Combined classes |
| `classes.save` | POST `set9.php` | W | class group/level/name/list/count and action fields |
| `timetable.form` | GET `teachers9.php?action=waktumengajar` | R | Timetable editor |
| `timetable.view` | GET `teachers9.php?action=viewjadual&user={user}` | R | Teacher timetable |
| `timetable.calendar` | GET `teachers9.php?action=calendar` | R | Academic calendar |
| `timetable.review` | GET `teachers9.php?action=semakjadual&setjadual={id}` | R | Review schedule |
| `timetable.save` | POST `teachers9.php` | W | session, school dates, periods, day/class/subject/time arrays |
| `timetable.activate` | POST `teachers9.php?action=aktifjadual` | W | Exact body form-dependent |
| `timetable.delete` | POST `teachers9.php?action=deletejadual` | D | Timetable id/token; form-dependent |
| `settings.instructional-profile` | GET `set9.php?action=InsPro` | R | Instructional-profile field selection |
| `settings.instructional-events` | GET `set9.php?action=FacPro` | R | Instructional-event phases |
| `settings.save` | POST `set9.php` | W | Selected settings plus action/set/context fields |
| `settings.competencies-info` | GET `set9.php?action=kompetensi` | R | Competency information |
| `settings.instructional-info` | GET `set9.php?action=instructional` | R | Instructional information |
| `settings.learning-profile-info` | GET `set9.php?action=learningprofile` | R | Learner-profile information |
| `settings.building-character` | GET `set9.php?action=buildingcharacter` | R | Character selections |
| `settings.developing-skills` | GET `set9.php?action=developingskills` | R | Skills selections |
| `settings.meta-learning` | GET `set9.php?action=instillingmetalearning` | R | Meta-learning selections |
| `settings.media` | GET `set9.php?action=media9` | R | Learner/media selections |
| `settings.modular` | GET `set9.php?action=modular` | R | Script-observed; schema unverified |
| `settings.reset` | POST `set9.php?action=resetsetting` | D | Scope/form unverified |

## Co-curricular

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `cocurricular.new-form` | GET `koku.php?action=start` | R | Planning/report form |
| `cocurricular.save` | POST `koku.php` | W | program, meeting, date/time/place, advisers, competencies, report/evidence fields |
| `cocurricular.list` | GET `koku.php?action=list` | R | program/month/year filters |
| `cocurricular.students-upload-form` | GET `kokuAddUser.php` | R | XLSX upload form/template |
| `cocurricular.students-upload` | POST `kokuAddUser.php` | W | `file`, action fields |
| `cocurricular.students-assign-form` | GET `kokuAddUser.php?action=assignstudent` | R | Assignment form |
| `cocurricular.students-assign` | GET same route with form parameters | W | `jenis_program`, `nama_program`, `do`; legacy GET may mutate |
| `cocurricular.weekly-attendance` | GET `kokuAddUser.php?action=weeklyattendance` | R | Weekly report UI |
| `cocurricular.attendance-save` | POST `kokuAddUser.php?action=attendance` | W | Attendance fields; form-dependent |
| `cocurricular.analysis` | GET `koku.php?action=analysis` | R | Overall attendance analysis |

## Lesson Study and SK@S

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `lesson-study.search` | GET `formsLS.php?action=searchmiw&sop=lessonstudy` | R | Search/filter source records |
| `lesson-study.list` | GET `formsLS.php?action=list` | R | teacher/month/year filters |
| `lesson-study.submit` | POST `formsLS.php` | W | Creation/update form; exact fields record-dependent |
| `skas.search` | GET `formsSKPM.php?action=searchmiw&sop=skpmg2` | R | Search source records |
| `skas.list` | GET `formsSKPM.php?action=list_SKPM` | R | teacher/session filters |
| `skas.form` | GET `formsSKPM.php?action=skpm&rph={rph}` | R | Evaluation form |
| `skas.submit` | POST `formsSKPM.php` | W | Evaluation body; form-dependent |

## Dashboard and reporting

| CLI function | Method and route | Risk | Observed purpose / parameters |
|---|---|---:|---|
| `dashboard` | GET `dashboard.php` | R | Individual statistics/DLP summary |
| `dashboard.detail` | GET `dashboard.php?action=detail&id={id}` | R | Unsubmitted DLP |
| `dashboard.required-hours` | GET `dashboard.php?action=detailmmi&id={id}` | R | Required subject hours |
| `dashboard.submitted` | GET `dashboard.php?action=submitteddetail&id={id}` | R | Submitted DLP |
| `dashboard.full` | GET `dashboard.php?action=fulldetail&id={id}` | R | All required DLP status |
| `dashboard.manual` | GET `dashboard.php?action=submittedmanual&id={id}` | R | Manually submitted DLP |

## Internal/script endpoints

| CLI function | Method and route | Risk | Observed contract |
|---|---|---:|---|
| `internal.keepalive` | GET `fetch_data.php` | R | Ten-minute session timer |
| `internal.miw-week` | POST `fetch_json.php` | R | `action=miwweek`, `get_selected=<date>` |
| `internal.questions` | GET `fetch_questions.php` | R | Parameters unverified |
| `internal.settings` | GET `fetch_setting.php` | R | Parameters unverified |
| `internal.lessons` | GET `get_lessons.php` | R | Parameters unverified |
| `internal.user-phone` | GET `fetch_user_phone.php?user_id={user_id}` | R | Sensitive contact data |
| `smart-search` | POST `fetch_smartsearch.php` JSON | W | `{id, category, selected}` → `{selectedOptions}`; may consume AI quota |
| `chat` | POST `chat.php` | W | Endpoint observed; payload unverified because direct browser load was blocked |

Additional script-observed action names are represented by the nearest guarded
registry function: `set9.php?action=create`, `media9`, `resetsetting`;
`teachers9.php?action=aktifjadual`, `deletejadual`; and
`upload.php?action=uploadRPH`, `uploadRefleksi`. Unknown forms are never promoted
to an unguarded raw call.
