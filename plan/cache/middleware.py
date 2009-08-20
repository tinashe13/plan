# Copyright 2009 Thomas Kongevold Adamcik
# 2009 IME Faculty Norwegian University of Science and Technology

# This file is part of Plan.
#
# Plan is free software: you can redistribute it and/or modify
# it under the terms of the Affero GNU General Public License as
# published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# Plan is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# Affero GNU General Public License for more details.
#
# You should have received a copy of the Affero GNU General Public
# License along with Plan.  If not, see <http://www.gnu.org/licenses/>.

import logging

class CacheMiddleware(object):
    '''Attaches either a real or dummy cache instance to our request, cache
       instance should only be used for retrival'''

    def __init__(self):
        self.logger = logging.getLogger('plan.middleware.cache')

    def process_request(self, request):
        request.use_cache = True

        if self._ignore_cache(request):
            self.logger.debug('Ignoring cache')
            request.use_cache = False

        return None

    def _ignore_cache(self, request):
        return (
            (request.user.is_authenticated() and
             request.META.get('HTTP_CACHE_CONTROL', '').lower() == 'no-cache') or
            'no-cache' in request.GET or
            'no-cache' in request.COOKIES
        )
