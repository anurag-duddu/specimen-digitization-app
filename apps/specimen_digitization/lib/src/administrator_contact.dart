/// Who "your administrator" is (screen blueprints, section 10; pass
/// criterion 10.3).
///
/// A message that tells a reviewer to ask their administrator and then names
/// nobody is not an instruction, it is a shrug. The collection document the
/// scope already carries is the only place the server publishes a contact, so
/// that is where this reads one from, and where it finds none it says which
/// collection the contact would be listed under rather than inventing a name.
library;

import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'models.dart';
import 'workspace.dart';

/// The keys a collection document may publish a contact under.
///
/// More than one, because the collection document is written by whoever set
/// the collection up rather than by this client, and the spellings in the
/// wild differ. Read in order; the first one that carries something wins.
const List<String> administratorContactKeys = <String>[
  'administrator_contact',
  'administrator',
  'support_contact',
  'support',
  'contact',
];

/// The keys a contact object may carry a reachable address under.
const List<String> administratorAddressKeys = <String>[
  'email',
  'address',
  'contact',
  'mailto',
];

/// The keys a contact object may carry a person or a role under.
const List<String> administratorNameKeys = <String>['name', 'role', 'team'];

/// The contact this build was stamped with (pass criterion 10.3).
///
/// The second of the two sources, and the one that works where the first
/// cannot: sign-in, setup and email verification are raised before any
/// collection is resolved, so there is no collection document to read a
/// contact out of. A deployment stamps this in and every "ask your
/// administrator" message in the product names somebody.
///
/// Accepted spellings, in the order they are tried:
///
/// - `Alex Mwangi <alex@example.org>`
/// - `Alex Mwangi, alex@example.org`
/// - `alex@example.org`
/// - `The entomology data team`
///
/// Empty by default, which is the honest state of a build nobody stamped:
/// the messages then say which collection the contact would be listed under,
/// exactly as they did before.
const String administratorContactDefine = String.fromEnvironment(
  'SPECIMEN_ADMIN_CONTACT',
);

/// The administrator of one collection, as the collection document names them.
@immutable
class AdministratorContact {
  const AdministratorContact({
    required this.collectionName,
    this.name,
    this.address,
  });

  /// The collection this contact belongs to, for the sentence that has to
  /// name it when there is no contact.
  final String collectionName;

  /// A person or a role: "Alex Mwangi", "the entomology data team".
  final String? name;

  /// A mail address the reviewer can write to.
  final String? address;

  /// True when the collection document named someone or something.
  bool get isKnown =>
      (name?.isNotEmpty ?? false) || (address?.isNotEmpty ?? false);

  /// Reads the contact out of [scope]'s collection document, or, where the
  /// document carries none, out of the build stamp.
  ///
  /// The collection document wins: a collection that names its own
  /// administrator knows better than a build-time default meant to cover
  /// every collection at once.
  static AdministratorContact of(CollectionScope? scope) {
    final String collection = scope?.name ?? scope?.key ?? 'this collection';
    final Json configuration =
        scope?.configuration ?? const <String, dynamic>{};
    for (final String key in administratorContactKeys) {
      final Object? raw = configuration[key];
      if (raw is String && raw.trim().isNotEmpty) {
        final String value = raw.trim();
        return value.contains('@')
            ? AdministratorContact(collectionName: collection, address: value)
            : AdministratorContact(collectionName: collection, name: value);
      }
      if (raw is Map) {
        final String? address = _first(raw, administratorAddressKeys);
        final String? name = _first(raw, administratorNameKeys);
        if (address != null || name != null) {
          return AdministratorContact(
            collectionName: collection,
            name: name,
            address: address,
          );
        }
      }
    }
    return fromBuild(collectionName: collection);
  }

  /// The contact this build was stamped with, or an unknown one.
  ///
  /// Used directly by the screens that are raised before a collection exists:
  /// sign-in, setup and email verification.
  static AdministratorContact fromBuild({
    String collectionName = 'this collection',
    String define = administratorContactDefine,
  }) {
    final String raw = define.trim();
    if (raw.isEmpty) {
      return AdministratorContact(collectionName: collectionName);
    }
    final RegExpMatch? angled = RegExp(r'^(.*?)<([^>]+)>$').firstMatch(raw);
    if (angled != null) {
      final String name = angled.group(1)!.trim();
      final String address = angled.group(2)!.trim();
      return AdministratorContact(
        collectionName: collectionName,
        name: name.isEmpty ? null : name,
        address: address.isEmpty ? null : address,
      );
    }
    final int comma = raw.lastIndexOf(',');
    if (comma > 0 && raw.substring(comma + 1).contains('@')) {
      return AdministratorContact(
        collectionName: collectionName,
        name: raw.substring(0, comma).trim(),
        address: raw.substring(comma + 1).trim(),
      );
    }
    return raw.contains('@')
        ? AdministratorContact(collectionName: collectionName, address: raw)
        : AdministratorContact(collectionName: collectionName, name: raw);
  }

  static String? _first(Map<Object?, Object?> source, List<String> keys) {
    for (final String key in keys) {
      final Object? value = source[key];
      if (value is String && value.trim().isNotEmpty) return value.trim();
    }
    return null;
  }

  /// The sentence that replaces "ask your administrator".
  ///
  /// Names a person or a role and a way to reach them where the collection
  /// document has one, and where it has none says exactly where a contact
  /// would be published rather than leaving the reviewer to guess.
  String get sentence {
    final String? who = name;
    final String? where = address;
    if (who != null && where != null) return 'Ask $who at $where.';
    if (where != null) return 'Ask your collection administrator at $where.';
    if (who != null) return 'Ask $who.';
    return 'Your collection administrator is listed in the collection '
        'configuration for $collectionName.';
  }

  /// A mail link carrying the collection and, where there is one, the record.
  ///
  /// Offered as text the reviewer can copy rather than a link this client
  /// opens: nothing in this app may hand a URL to the platform without the
  /// reviewer choosing it.
  String subjectFor({String? specimenId}) => specimenId == null
      ? 'Specimen digitization, collection $collectionName'
      : 'Specimen digitization, collection $collectionName, record $specimenId';

  /// The whole mail link, address and subject, or null without an address.
  ///
  /// Carries the record when one is open, so the administrator is not asked
  /// to work out which specimen the message is about.
  String? mailtoFor({String? specimenId}) {
    final String? to = address;
    if (to == null || to.isEmpty) return null;
    return Uri(
      scheme: 'mailto',
      path: to,
      queryParameters: <String, String>{
        'subject': subjectFor(specimenId: specimenId),
      },
    ).toString();
  }
}

/// One line naming the administrator, read from the open collection.
///
/// Reads the workspace itself rather than taking the contact as an argument,
/// so a message buried six widgets deep can name a person without six widgets
/// growing a parameter. Outside the collection shell there is no collection
/// document, and the line says which collection the contact is listed under.
class AdministratorContactLine extends StatelessWidget {
  const AdministratorContactLine({
    super.key,
    this.specimenId,
    this.dense = true,
  });

  /// The record the message is about, put in the mail subject.
  final String? specimenId;

  /// True for the small print beside another message, false for the help
  /// sheet where this is a section of its own.
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final WorkspaceScope? scope = context
        .getInheritedWidgetOfExactType<WorkspaceScope>();
    // Outside the collection shell there is no scope at all, and
    // `AdministratorContact.of(null)` falls through to the build stamp, which
    // is the whole point of the stamp (pass criterion 10.3).
    final AdministratorContact contact = AdministratorContact.of(
      scope?.notifier?.scope,
    );
    final TextStyle style = dense
        ? ui.type.bodySmall.copyWith(color: ui.color.inkSecondary)
        : ui.type.body.copyWith(color: ui.color.ink);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(contact.sentence, style: style),
        if (contact.mailtoFor(specimenId: specimenId)
            case final String link) ...<Widget>[
          SizedBox(height: ui.space.s1),
          // The whole link, address and subject, copied rather than opened:
          // nothing in this app hands a URL to the platform without the
          // reviewer choosing it. The copy control is what replaced the
          // selectable run of text, which was a Material component.
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Expanded(
                child: Text(
                  link,
                  style: ui.type.mono.identifier.copyWith(
                    color: ui.color.inkSecondary,
                  ),
                ),
              ),
              UiIconButton(
                icon: UiIcons.copy,
                semanticsLabel: copyLabel,
                tooltip: copyLabel,
                onPressed: () =>
                    unawaited(Clipboard.setData(ClipboardData(text: link))),
              ),
            ],
          ),
        ],
      ],
    );
  }

  /// What the copy control is called.
  static const String copyLabel = 'Copy the mail link';
}
