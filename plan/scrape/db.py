# encoding: utf-8

import logging
import re
from decimal import Decimal


from django.db import transaction
from django.conf import settings

from plan.common.models import Course, Lecture, Lecturer, Semester, Group, \
        Type, Week, Room

logger = logging.getLogger('scrape.db')

def _prefix(semester):
    if semester.type == Semester.SPRING:
        return 'v%s' % str(semester.year)[-2:]
    else:
        return 'h%s' % str(semester.year)[-2:]

def _connection():
    import MySQLdb

    mysql_setings = {
        'db': settings.MYSQL_NAME,
        'host': settings.MYSQL_HOST,
        'user': settings.MYSQL_USER,
        'passwd': settings.MYSQL_PASSWORD,
        'use_unicode': True,
    }

    return MySQLdb.connect(**mysql_setings)

@transaction.commit_on_success
def update_lectures(year, semester_type, prefix=None, limit=None):
    '''Retrive all lectures for a given course'''

    semester, created = Semester.objects.get_or_create(year=year, type=semester_type)

    prefix = prefix or _prefix(semester)

    logger.debug('Using prefix: %s', prefix)

    db = _connection()
    c = db.cursor()

    query = """
            SELECT emnekode,typenavn,dag,start,slutt,uke,romnavn,larer,aktkode
            FROM %s_timeplan WHERE emnekode NOT LIKE '#%%'
        """ % prefix

    if limit:
        logger.info('Limiting to %s*', limit)

        query  = query.replace('%', '%%')
        query += ' AND emnekode LIKE %s'
        c.execute(query, (limit+'%',))
    else:
        c.execute(query)

    added_lectures = []
    mysql_lecture_count = 0

    lectures = Lecture.objects.filter(semester=semester)

    if limit:
        lectures = lectures.filter(course__name__startswith=limit)

    for l in lectures:
        l.rooms.clear()
        l.weeks.clear()
        l.lecturers.clear()

    for row in c.fetchall():
        code, course_type, day, start, end, week, room, lecturer, groupcode = row
        if not code.strip():
            continue

        mysql_lecture_count += 1

        # Remove -1 etc. from course code
        code = '-'.join(code.split('-')[:-1]).upper()

        # Get and or update course
        course, created = Course.objects.get_or_create(name=code)
        course.semesters.add(semester)

        # Load or create type:
        if course_type:
            course_type, created = Type.objects.get_or_create(name=course_type)

        # Figure out day mapping
        try:
            day = ['mandag', 'tirsdag', 'onsdag', 'torsdag', 'fredag'].index(day)
        except ValueError:
            logger.warning("Could not add %s - %s on %s for %s" % (start, end, day, course))
            continue

        # Figure out times:

        # We choose to be slightly naive and only care about which hour
        # something starts.
        try:
            start_slot = dict(map(lambda x: (int(x[1].split(':')[0]), x[0]),
                    Lecture.START))[int(start.split(':')[0])]
            end_slot = dict(map(lambda x: (int(x[1].split(':')[0]), x[0]),
                    Lecture.END))[int(end.split(':')[0])]
        except KeyError, e:
            if int(end.split(':')[0]) == 8:
                logger.info("Converting %s to 09:00 for %s" % (end, course))
                end_slot = 9
            elif int(end.split(':')[0]) == 0:
                logger.info("Converting %s to 20:00 for %s" % (end, course))
                end_slot = Lecture.END[-1][0]
            else:
                logger.warning("Could not add %s - %s on %s for %s" % (start, end, day, course))
                continue

        # Rooms:
        rooms = []
        for r in room.split('#'):
            if r.strip():
                r, created = Room.objects.get_or_create(name=r)
                rooms.append(r)

        # Groups:
        groups = []
        c2 = db.cursor()
        c2.execute("""
                SELECT DISTINCT asp.studieprogramkode
                FROM %s_akt_studieprogram asp,studieprogram sp
                WHERE asp.studieprogramkode=sp.studieprogram_kode
                AND asp.aktkode = %%s
            """ % prefix, groupcode)
        for group in c2.fetchall():
            group, created = Group.objects.get_or_create(name=group[0])
            groups.append(group)

        if not groups:
            group, created = Group.objects.get_or_create(name=Group.DEFAULT)
            groups = [group]

        # Weeks
        # FIXME seriosuly this generates way to many db queries...
        weeks = []
        for w in re.split(r',? ', week):
            if '-' in w:
                x, y = w.split('-')
                for i in range(int(x), int(y)+1):
                    w2 = Week.objects.get(number=i)
                    weeks.append(w2)
            elif w.isdigit():
                w2 = Week.objects.get(number=w)
                weeks.append(w2)
            else:
                logger.warning("Messed up week '%s' for %s" % (w, course))

        # Lecturer:
        lecturers = []
        for l in lecturer.split('#'):
            if l.strip():
                lecturer, created = Lecturer.objects.get_or_create(
                        name=l.strip())
                lecturers.append(lecturer)

        lecture_kwargs = {
            'course': course,
            'day': day,
            'start_time': start_slot,
            'end_time': end_slot,
            'semester': semester,
            'type': course_type,
        }

        if not course_type:
            del lecture_kwargs['type']

        lectures = Lecture.objects.filter(**lecture_kwargs)
        lectures = lectures.exclude(id__in=added_lectures)

        added = False

        for lecture in lectures:
            psql_set = set(lecture.groups.values_list('id', flat=True))
            mysql_set = set(map(lambda g: g.id, groups))

            if psql_set == mysql_set:
                # FIXME need extra check against weeks and rooms
                lecture.rooms = rooms
                lecture.weeks = weeks
                lecture.lecturers = lecturers

                added_lectures.append(lecture.id)
                added = True
                break

        if not added:
            lecture = Lecture(**lecture_kwargs)
            lecture.save()

            added_lectures.append(lecture.id)

            # Simply set data since we are saving new lecture
            lecture.groups = groups
            lecture.rooms = rooms
            lecture.weeks = weeks
            lecture.lecturers = lecturers

        lecture.start = start
        lecture.end = end
        lecture.save()

        # FIXME this is backward
        if added:
            logger.debug('%s saved', Lecture.objects.get(pk=lecture.pk))
        else:
            logger.debug('%s added', Lecture.objects.get(pk=lecture.pk))

    to_remove =  Lecture.objects.exclude(id__in=added_lectures). \
            filter(semester=semester)

    if limit:
        to_remove = to_remove.filter(course__name__startswith=limit)

    logger.info('%d lectures in source db, %d in destination', mysql_lecture_count, len(added_lectures))

    return to_remove

def update_courses(year, semester_type, prefix=None):
    semester, created = Semester.objects.get_or_create(year=year, type=semester_type)

    prefix = prefix or _prefix(semester)

    db = _connection()
    c = db.cursor()

    c.execute("""SELECT emnekode,emnenavn,vekt FROM %s_fs_emne WHERE emnekode
            NOT LIKE '#%%'""" % prefix)

    for code, name, points in c.fetchall():
        if not code.strip():
            continue

        code = ''.join(code.split('-')[:-1]).upper().strip()

        if name[0] in ['"', "'"] and name[0] == name[-1]:
            name = name[1:-1]

        course, created = Course.objects.get_or_create(name=code)

        if points:
            course.points = Decimal(points.strip().replace(',', '.'))
        course.full_name = name
        course.save()

        if created:
            logger.info("Added course %s" % course.name)
        else:
            logger.info("Updated course %s" % course.name)
