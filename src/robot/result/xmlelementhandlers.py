#  Copyright 2008-2015 Nokia Networks
#  Copyright 2016-     Robot Framework Foundation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

from robot.errors import DataError


class XmlElementHandler(object):

    def __init__(self, execution_result, root_handler=None):
        self._stack = [(root_handler or RootHandler(), execution_result)]

    def start(self, elem):
        handler, result = self._stack[-1]
        handler = handler.get_child_handler(elem)
        result = handler.start(elem, result)
        self._stack.append((handler, result))

    def end(self, elem):
        handler, result = self._stack.pop()
        handler.end(elem, result)


class ElementHandler(object):
    element_handlers = {}
    tag = None
    children = frozenset()

    @classmethod
    def register(cls, handler):
        cls.element_handlers[handler.tag] = handler()
        return handler

    def get_child_handler(self, elem):
        if elem.tag not in self.children:
            if not self.tag:
                raise DataError("Incompatible root element '%s'." % elem.tag)
            raise DataError("Incompatible child element '%s' for '%s'."
                            % (elem.tag, self.tag))
        return self.element_handlers[elem.tag]

    def start(self, elem, result):
        return result

    def end(self, elem, result):
        pass

    def _timestamp(self, elem, attr_name):
        timestamp = elem.get(attr_name)
        return timestamp if timestamp != 'N/A' else None


class RootHandler(ElementHandler):
    children = frozenset(('robot',))


@ElementHandler.register
class RobotHandler(ElementHandler):
    tag = 'robot'
    children = frozenset(('suite', 'statistics', 'errors'))

    def start(self, elem, result):
        generator = elem.get('generator', 'unknown').split()[0].upper()
        result.generated_by_robot = generator == 'ROBOT'
        if result.rpa is None:
            result.rpa = elem.get('rpa', 'false') == 'true'
        return result


@ElementHandler.register
class SuiteHandler(ElementHandler):
    tag = 'suite'
    children = frozenset(('doc', 'metadata', 'status', 'kw', 'test', 'suite'))

    def start(self, elem, result):
        if hasattr(result, 'suite'):    # root
            return result.suite.config(name=elem.get('name', ''),
                                       source=elem.get('source'),
                                       rpa=result.rpa)
        return result.suites.create(name=elem.get('name', ''),
                                    source=elem.get('source'),
                                    rpa=result.rpa)

    def get_child_handler(self, elem):
        if elem.tag == 'status':
            return StatusHandler(set_status=False)
        return ElementHandler.get_child_handler(self, elem)


@ElementHandler.register
class TestHandler(ElementHandler):
    tag = 'test'
    children = frozenset(('doc', 'tags', 'timeout', 'status', 'kw', 'if'))

    def start(self, elem, result):
        return result.tests.create(name=elem.get('name', ''))


@ElementHandler.register
class KeywordHandler(ElementHandler):
    tag = 'kw'
    children = frozenset(('doc', 'arguments', 'assign', 'tags', 'timeout',
                          'status', 'msg', 'kw', 'if'))

    def start(self, elem, result):
        creator = getattr(self, '_create_%s' % elem.get('type', 'kw'))
        return creator(elem, result)

    def _create_kw(self, elem, result):
        return result.body.create_keyword(kwname=elem.get('name', ''),
                                          libname=elem.get('library', ''),
                                          type=elem.get('type', 'kw'))    # FIXME: Remove type here

    def _create_setup(self, elem, result):
        return result.setup.config(kwname=elem.get('name', ''),
                                   libname=elem.get('library', ''))

    def _create_teardown(self, elem, result):
        return result.teardown.config(kwname=elem.get('name', ''),
                                      libname=elem.get('library', ''))

    def _create_if(self, elem, result):
        return result.body.create_if(condition=elem.get('name'))

    def _create_elseif(self, elem, result):
        return self._config_orelse(result.body[-1].orelse, elem.get('name'))

    def _config_orelse(self, orelse, condition=None):
        # In output.xml IF branches are in sequence but in model they are nested.
        # 'orelse' we got is the first ELSE (IF) branch and we need to find
        # the correct one configure i.e. the one that isn't yet configured.
        # Reorganizing output.xml might be a good idea.
        while orelse:
            orelse = orelse.orelse
        orelse.config(condition=condition)
        return orelse

    def _create_else(self, elem, result):
        return self._config_orelse(result.body[-1].orelse)

    def _create_for(self, elem, result):
        return self._create_kw(elem, result)

    def _create_foritem(self, elem, result):
        return self._create_kw(elem, result)


@ElementHandler.register
class MessageHandler(ElementHandler):
    tag = 'msg'

    def end(self, elem, result):
        result.body.create_message(elem.text or '',
                                   elem.get('level', 'INFO'),
                                   elem.get('html', 'no') == 'yes',
                                   self._timestamp(elem, 'timestamp'))


@ElementHandler.register
class StatusHandler(ElementHandler):
    tag = 'status'

    def __init__(self, set_status=True):
        self.set_status = set_status

    def end(self, elem, result):
        if self.set_status:
            result.status = elem.get('status', 'FAIL')
        result.starttime = self._timestamp(elem, 'starttime')
        result.endtime = self._timestamp(elem, 'endtime')
        if elem.text:
            result.message = elem.text


@ElementHandler.register
class DocHandler(ElementHandler):
    tag = 'doc'

    def end(self, elem, result):
        result.doc = elem.text or ''


@ElementHandler.register
class MetadataHandler(ElementHandler):
    tag = 'metadata'
    children = frozenset(('item',))


@ElementHandler.register
class MetadataItemHandler(ElementHandler):
    tag = 'item'

    def end(self, elem, result):
        result.metadata[elem.get('name', '')] = elem.text or ''


@ElementHandler.register
class TagsHandler(ElementHandler):
    tag = 'tags'
    children = frozenset(('tag',))


@ElementHandler.register
class TagHandler(ElementHandler):
    tag = 'tag'

    def end(self, elem, result):
        result.tags.add(elem.text or '')


@ElementHandler.register
class TimeoutHandler(ElementHandler):
    tag = 'timeout'

    def end(self, elem, result):
        result.timeout = elem.get('value')


@ElementHandler.register
class AssignHandler(ElementHandler):
    tag = 'assign'
    children = frozenset(('var',))


@ElementHandler.register
class AssignVarHandler(ElementHandler):
    tag = 'var'

    def end(self, elem, result):
        result.assign += (elem.text or '',)


@ElementHandler.register
class ArgumentsHandler(ElementHandler):
    tag = 'arguments'
    children = frozenset(('arg',))


@ElementHandler.register
class ArgumentHandler(ElementHandler):
    tag = 'arg'

    def end(self, elem, result):
        result.args += (elem.text or '',)


@ElementHandler.register
class ErrorsHandler(ElementHandler):
    tag = 'errors'

    def start(self, elem, result):
        return result.errors

    def get_child_handler(self, elem):
        return ErrorMessageHandler()


class ErrorMessageHandler(ElementHandler):

    def end(self, elem, result):
        result.messages.create(elem.text or '',
                               elem.get('level', 'INFO'),
                               elem.get('html', 'no') == 'yes',
                               self._timestamp(elem, 'timestamp'))


@ElementHandler.register
class StatisticsHandler(ElementHandler):
    tag = 'statistics'

    def get_child_handler(self, elem):
        return self
