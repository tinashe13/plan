from django.utils.datastructures import MultiValueDict

from plan.common.tests.base import BaseTestCase
from plan.common.cache import get_realm, cache
from plan.common.models import Semester, Group, UserSet, Lecture

class EmptyViewTestCase(BaseTestCase):
    def test_index(self):
        response = self.client.get(self.url_basic('frontpage'))

        self.failUnlessEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'start.html')

    def test_shortcut(self):
        response = self.client.get(self.url('shortcut', 'adamcik'))

        self.failUnlessEqual(response.status_code, 404)
        self.assertTemplateUsed(response, '404.html')

class ViewTestCase(BaseTestCase):
    fixtures = ['test_data.json', 'test_user.json']

    # FIXME check what happens when we do GET against change functions

    def test_index(self):
        # Load page
        response = self.client.get(self.url_basic('frontpage'))
        self.failUnlessEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'start.html')

        # Check that cache gets set
        realm = get_realm(self.semester)
        cached_response = cache.get('frontpage', realm=realm)

        self.assertEquals(True, cached_response is not None)
        self.assertEquals(response.content, cached_response.content)

        # Check that cache gets cleared
        self.clear()
        cached_response = cache.get('frontpage', realm=realm)

        self.assertEquals(cached_response, None)

        semester = self.semester
        args = [semester.year, semester.get_type_display()]
        response = self.client.get(self.url('frontpage-semester', *args))
        self.failUnlessEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'start.html')

        # FIXME test posting to index
        # FIXME test missing code 76

    def test_shortcut(self):
        response = self.client.get(self.url('shortcut', 'adamcik'))
        self.assertRedirects(response, self.url('schedule'))

    def test_schedule(self):
        # FIXME add group help testing
        # FIXME courses without lectures
        # FIXME test next semester message
        # FIXME test cache time for deadlines etc
        # FIXME test group-help message

        s = self.semester

        week = 1
        for name in ['schedule', 'schedule-advanced', 'schedule-week', 'schedule-week', 'schedule-all']:
            args = [s.year, s.get_type_display(), 'adamcik']

            if name.endswith('week'):
                args.append(week)
                week += 1

            if name in ['schedule', 'schedule-all']:
                week = 1
                args.append(week)
                name = 'schedule-week'

            url = self.url(name, *args)

            response = self.client.get(url)
            self.assertEquals(response.status_code, 200)
            self.assertTemplateUsed(response, 'schedule.html')

            # Check twice to test cache code 
            response = self.client.get(url)
            self.assertEquals(response.status_code, 200)

            cache_response = self.get(url)
            self.assertEquals(response.content, cache_response.content)

            self.clear()
            cache_response = self.get(url)

            self.assertEquals(cache_response, None)

    def test_course_list(self):
        # FIXME test POST

        s = Semester.current()
        url = self.url('course-list')
        key = '/'.join([str(s.year), s.get_type_display(), 'courses'])

        response = self.client.get(url)
        self.failUnlessEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'course_list.html')

        cache_response = cache.get(key, prefix=True)
        self.assertEquals(response.content, cache_response.content)

        self.clear()
        cache_response = cache.get(key, prefix=True)

        self.assertEquals(response.content, cache_response.content)

    def test_change_course(self):
        # FIXME test semester does not exist
        # FIXME test ie handling
        # FIXME test invalid course
        # FIXME test more that 20 warning
        # FIXME test group-help
        # FIXME test error.html

        original_url = self.url('schedule-advanced')
        url = self.url('change-course')

        post_data = [
            {'submit_add': True,
             'course_add': 'COURSE4'},
            {'submit_name': True,
             '4-name': 'foo'},
            {'submit_name': True,
             '4-name': 'foo bar baz foo bar baz foo bar baz ' + \
                       'foo bar baz foo bar baz foo bar baz'},
            {'submit_remove': True,
             'course_remove': 4},
        ]

        usersets = list(UserSet.objects.filter(slug='adamcik').order_by('id').values_list())

        for data in post_data:
            original_response = self.client.get(original_url)

            response = self.client.post(url, data)

            self.assertEquals(response.status_code, 302)
            self.assert_(response['Location'].endswith(original_url))

            cache_response = self.get(original_url)
            self.assertEquals(cache_response, None)

            response = self.client.get(original_url)
            self.assert_(original_response.content != response.content)

            self.clear()

            new_usersets = list(UserSet.objects.filter(slug='adamcik').order_by('id').values_list())
            self.assert_(new_usersets != usersets)

            usersets = new_usersets

    def test_change_groups(self):
        # FIXME test for courses without groups

        original_url = self.url('schedule-advanced')
        url = self.url('change-groups')

        post_data = [
            {'1-groups': '1',
             '2-groups': '',
             '3-groups': '2'},
            {'1-groups': '',
             '2-groups': '',
             '3-groups': ''},
            {'1-groups': ('1','2'),
             '2-groups': '',
             '3-groups': '2'}
        ]

        groups = list(Group.objects.filter(userset__slug='adamcik').order_by('id').values_list())

        for data in post_data:
            original_response = self.client.get(original_url)

            response = self.client.post(url, MultiValueDict(data))

            self.assert_(response['Location'].endswith(original_url))
            self.assertEquals(response.status_code, 302)

            cache_response = self.get(original_url)
            self.assertEquals(cache_response, None)

            response = self.client.get(original_url)
            self.assert_(original_response.content != response.content)

            self.clear()

            new_groups = list(Group.objects.filter(userset__slug='adamcik').order_by('id').values_list())
            self.assert_(groups != new_groups)

            groups = new_groups


    def test_change_lectures(self):
        # FIXME test nulling out excludes

        original_url = self.url('schedule-advanced')
        url = self.url('change-lectures')

        post_data = [
            {'exclude': ('2', '3', '8')},
            {'exclude': ('2')},
            #{}, # FIXME add to test
            {'exclude': ('2', '3', '8', '9', '7', '10', '11', '4', '5', '6')},
            {'exclude': ('2')},
            {'exclude': ('2', '3', '8')},
        ]

        lectures = list(Lecture.objects.filter(excluded_from__slug='adamcik').order_by('id').values_list())

        for data in post_data:
            original_response = self.client.get(original_url)

            response = self.client.post(url, MultiValueDict(data))

            self.assert_(response['Location'].endswith(original_url))
            self.assertEquals(response.status_code, 302)

            cache_response = self.get(original_url)
            self.assertEquals(cache_response, None)

            response = self.client.get(original_url)
            self.assert_(original_response.content != response.content)

            self.clear()

            new_lectures = list(Lecture.objects.filter(excluded_from__slug='adamcik').order_by('id').values_list())
            self.assert_(lectures != new_lectures)

            lectures = new_lectures

    def test_new_deadline(self):
        pass
        # FIXME

    def test_copy_deadlines(self):
        pass
        # FIXME