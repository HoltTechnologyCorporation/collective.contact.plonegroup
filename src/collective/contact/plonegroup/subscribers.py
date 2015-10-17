# -*- coding: utf-8 -*-
from Acquisition import aq_get
from zExceptions import Redirect
from zope.component import getUtility, getMultiAdapter
from zope.interface import alsoProvides, Interface, noLongerProvides
from zope.lifecycleevent.interfaces import IObjectRemovedEvent
from zope.schema import getFieldsInOrder
from zope.schema.interfaces import ICollection, IText, IChoice

from plone import api
from plone.app.linkintegrity.interfaces import ILinkIntegrityInfo
from plone.app.linkintegrity.handlers import referencedObjectRemoved as baseReferencedObjectRemoved
from plone.behavior.interfaces import IBehavior
from plone.dexterity.interfaces import IDexterityContent, IDexterityFTI
from plone.registry.interfaces import IRegistry

from Products.CMFPlone.utils import base_hasattr
from Products.statusmessages.interfaces import IStatusMessage

from . import _
from config import PLONEGROUP_ORG, ORGANIZATIONS_REGISTRY
from interfaces import IPloneGroupContact, INotPloneGroupContact

try:
    from plone.app.referenceablebehavior.referenceable import IReferenceable
except ImportError:
    class IReferenceable(Interface):
        pass


def search_value_in_objects(s_obj, ref, p_types=[], type_fields={}):
    """
        Searching a value (reference to an object like id or uid) in fields of objects.
        Parameters:
            * s_obj : the object that is maybe referenced in another objects fields
            * ref : the value to search in field
            * p_types : portal_types that will be only searched
            * type_fields : dict containing as key portal_type and as value a list of fields that must be searched.
                            If a portal_type is not given, all fields will be searched
    """
    # we check all dexterity objects fields to see if ref is used in
    # we can't check only fields using plonegroup vocabulary because maybe another vocabulary name is used
    # this can be long but this operation is not made so often

    request = aq_get(s_obj, 'REQUEST', None)
    if not request:
        return
    try:
        catalog = api.portal.get_tool('portal_catalog')
    except api.portal.CannotGetPortalError:
        # When deleting site, the portal is no more found...
        return

    storage = ILinkIntegrityInfo(request)

    def list_fields(ptype, filter_interfaces=(IText, ICollection, IChoice)):
        """ return for the portal_type the selected fields """
        if ptype not in type_fields:
            type_fields[ptype] = []
            fti = getUtility(IDexterityFTI, name=ptype)
            for name, fld in getFieldsInOrder(fti.lookupSchema()):
                for iface in filter_interfaces:
                    if iface.providedBy(fld):
                        type_fields[ptype].append(name)
                        break
            # also lookup behaviors
            for behavior_id in fti.behaviors:
                behavior = getUtility(IBehavior, behavior_id).interface
                for name, fld in getFieldsInOrder(behavior):
                    for iface in filter_interfaces:
                        if iface.providedBy(fld):
                            type_fields[ptype].append(name)
                            break
        return type_fields[ptype]

    def check_value(val):
        if isinstance(val, basestring) and val == ref:
            return True
        return False

    def check_attribute(val):
        """ check the attribute value and walk in it """
        if isinstance(val, dict):
            for v in val.values():
                res = check_attribute(v)
                if res:
                    return res
        elif base_hasattr(val, '__iter__'):
            for v in val:
                res = check_attribute(v)
                if res:
                    return res
        elif check_value(val):
            res = [val]
            return res
        return []

    for brain in catalog.searchResults(portal_types=p_types, object_provides=IDexterityContent.__identifier__):
        obj = brain.getObject()
        ptype = obj.portal_type
        for attr in list_fields(ptype):
            if base_hasattr(obj, attr):
                res = check_attribute(getattr(obj, attr))
                if res:
                    storage.addBreach(obj, s_obj)
                    break


def plonegroupOrganizationRemoved(del_obj, event):
    """
        Store information about the removed organization integrity.
    """
    # inspired from z3c/relationfield/event.py:breakRelations
    # and plone/app/linkintegrity/handlers.py:referenceRemoved
    # if the object the event was fired on doesn't have a `REQUEST` attribute
    # we can safely assume no direct user action was involved and therefore
    # never raise a link integrity exception...

    search_value_in_objects(del_obj, del_obj.UID(), p_types=[], type_fields={})


def referencedObjectRemoved(obj, event):
    if not IReferenceable.providedBy(obj):
        baseReferencedObjectRemoved(obj, event)


def plonegroup_contact_transition(contact, event):
    """
        React when a IPloneGroupContact transition is done
    """
    if event.transition.id == 'deactivate':
        # check if the transition is selected
        registry = getUtility(IRegistry)
        errors = []
        if contact.UID() in registry[ORGANIZATIONS_REGISTRY]:
            errors.append(_('This contact is selected in configuration'))
        else:
            search_value_in_objects(contact, contact.UID(), p_types=[], type_fields={})
            storage = ILinkIntegrityInfo(contact.REQUEST)
            breaches = storage.getIntegrityBreaches()
            if contact in breaches:
                errors.append(_("This contact is used in following content: ${items}",
                                mapping={'items': ', '.join(['<a href="%s" target="_blank">%s</a>'
                                                             % (i.absolute_url(), i.Title())
                                                             for i in breaches[contact]])}))
        if errors:
            smi = IStatusMessage(contact.REQUEST)
            smi.addStatusMessage(_('You cannot deactivate this item !'), type='error')
            smi.addStatusMessage(errors[0], type='error')
            view_url = getMultiAdapter((contact, contact.REQUEST), name=u'plone_context_state').view_url()
            #contact.REQUEST['RESPONSE'].redirect(view_url)
            raise Redirect(view_url)


def mark_organization(contact, event):
    """ Set a marker interface on contact content. """
    if IObjectRemovedEvent.providedBy(event):
        return
    if '/%s' % PLONEGROUP_ORG in contact.absolute_url_path():
        if not IPloneGroupContact.providedBy(contact):
            alsoProvides(contact, IPloneGroupContact)
        if INotPloneGroupContact.providedBy(contact):
            noLongerProvides(contact, INotPloneGroupContact)
    else:
        if not INotPloneGroupContact.providedBy(contact):
            alsoProvides(contact, INotPloneGroupContact)
        if IPloneGroupContact.providedBy(contact):
            noLongerProvides(contact, IPloneGroupContact)

    contact.reindexObject(idxs='object_provides')
