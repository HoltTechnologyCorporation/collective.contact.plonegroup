# -*- coding: utf-8 -*-
"""Setup/installation tests for this package."""

from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory
from plone import api
from plone.registry.interfaces import IRegistry
from collective.contact.plonegroup.testing import IntegrationTestCase
from ..config import ORGANIZATIONS_REGISTRY, FUNCTIONS_REGISTRY


class TestInstall(IntegrationTestCase):
    """Test installation of collective.contact.plonegroup into Plone."""

    def setUp(self):
        """Custom shared utility setup for tests."""
        self.portal = self.layer['portal']
        # Organizations creation
        self.portal.invokeFactory('directory', 'contacts')
        self.portal['contacts'].invokeFactory('organization', 'plonegroup-organization', title='My organization')
        own_orga = self.portal['contacts']['plonegroup-organization']
        own_orga.invokeFactory('organization', 'department1', title='Department 1')
        own_orga.invokeFactory('organization', 'department2', title='Department 2')
        own_orga['department1'].invokeFactory('organization', 'service1', title='Service 1')

        self.registry = getUtility(IRegistry)
        self.registry['collective.contact.plonegroup.browser.settings.IContactPlonegroupConfig.'
                      'organizations'] = [own_orga['department1'].UID(),
                                          own_orga['department1']['service1'].UID(),
                                          own_orga['department2'].UID()]
        self.registry['collective.contact.plonegroup.browser.settings.IContactPlonegroupConfig.'
                      'functions'] = [{'fct_title': u'Director',
                                       'fct_id': u'director'},
                                      {'fct_title': u'Worker',
                                       'fct_id': u'worker'}]

    def test_OwnOrganizationServicesVocabulary(self):
        """"""
        services = getUtility(IVocabularyFactory, name=u'collective.contact.plonegroup.organization_services')
        voc_dic = services(self).by_token
        voc_list = [voc_dic[key].title for key in voc_dic.keys()]
        self.assertEquals(voc_list, ['Department 1 - Service 1', 'Department 1', 'Department 2'])
        # When multiple own organizations
        self.portal['contacts'].invokeFactory('organization', 'temporary', title='Temporary')
        self.portal['contacts']['temporary'].invokeFactory('organization', 'plonegroup-organization',
                                                           title='Duplicated organization')
        services = getUtility(IVocabularyFactory, name=u'collective.contact.plonegroup.organization_services')
        voc_dic = services(self).by_token
        voc_list = [voc_dic[key].title for key in voc_dic.keys()]
        self.assertEquals(voc_list, ["You must have only one organization with id 'plonegroup-organization' !"])
        # When own organization not found
        self.portal['contacts'].manage_delObjects(ids=['plonegroup-organization'])
        self.portal['contacts'].manage_delObjects(ids=['temporary'])
        services = getUtility(IVocabularyFactory, name=u'collective.contact.plonegroup.organization_services')
        voc_dic = services(self).by_token
        voc_list = [voc_dic[key].title for key in voc_dic.keys()]
        self.assertEquals(voc_list, ["You must define an organization with id 'plonegroup-organization' !"])

    def test_detectContactPlonegroupChange(self):
        """Test if group creation works correctly"""
        group_ids = [group.id for group in api.group.get_groups()]
        organizations = self.registry[ORGANIZATIONS_REGISTRY]
        for uid in organizations:
            self.assertIn('%s_director' % uid, group_ids)
            self.assertIn('%s_worker' % uid, group_ids)
        d1_d_group = api.group.get(groupname='%s_director' % organizations[0])
        self.assertEquals(d1_d_group.getProperty('title'), 'Department 1 (Director)')
        d1s1_d_group = api.group.get(groupname='%s_director' % organizations[1])
        self.assertEquals(d1s1_d_group.getProperty('title'), 'Department 1 - Service 1 (Director)')
        # Changing organization title
        # To be updated when event added
        #self.assertEquals(d1_d_group.getProperty('title'), 'Work service (Director)')
        # Changing function title
        self.registry[FUNCTIONS_REGISTRY] = [{'fct_title': u'Directors', 'fct_id': u'director'},
                                             {'fct_title': u'Worker', 'fct_id': u'worker'}]
        d1_d_group = api.group.get(groupname='%s_director' % organizations[0])
        self.assertEquals(d1_d_group.getProperty('title'), 'Department 1 (Directors)')
        d1s1_d_group = api.group.get(groupname='%s_director' % organizations[1])
        self.assertEquals(d1s1_d_group.getProperty('title'), 'Department 1 - Service 1 (Directors)')
        # Adding new organization
        own_orga = self.portal['contacts']['plonegroup-organization']
        own_orga['department2'].invokeFactory('organization', 'service2', title='Service 2')
        # append() method on the registry doesn't trigger the event. += too
        newValue = self.registry[ORGANIZATIONS_REGISTRY] + [own_orga['department2']['service2'].UID()]
        self.registry[ORGANIZATIONS_REGISTRY] = newValue
        group_ids = [group.id for group in api.group.get_groups()]
        last_uid = self.registry[ORGANIZATIONS_REGISTRY][-1]
        self.assertIn('%s_director' % last_uid, group_ids)
        self.assertIn('%s_worker' % last_uid, group_ids)
        # Adding new function
        newValue = self.registry[FUNCTIONS_REGISTRY] + [{'fct_title': u'Chief', 'fct_id': u'chief'}]
        self.registry[FUNCTIONS_REGISTRY] = newValue
        group_ids = [group.id for group in api.group.get_groups() if '_' in group.id]
        self.assertEquals(len(group_ids), 12)
        for uid in self.registry[ORGANIZATIONS_REGISTRY]:
            self.assertIn('%s_director' % uid, group_ids)
            self.assertIn('%s_chief' % uid, group_ids)
            self.assertIn('%s_worker' % uid, group_ids)
