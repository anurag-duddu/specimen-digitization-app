/// The person disc (10 section 4.5, `UiAvatar`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../primitives/label.dart';

/// The two avatar diameters 10 section 4.5 names.
enum UiAvatarSize {
  /// 32. Inside a row, beside a decision.
  small(32),

  /// 40. In the account menu and at the head of a history entry.
  medium(40);

  const UiAvatarSize(this.diameter);

  /// The disc's diameter in logical pixels.
  final double diameter;
}

/// The resolved paint of one avatar.
@immutable
class UiAvatarStyle {
  /// Binds every token an avatar draws with.
  const UiAvatarStyle({
    required this.fill,
    required this.foreground,
    required this.initials,
    required this.diameter,
  });

  /// The disc behind the initials.
  final Color fill;

  /// The initials themselves.
  final Color foreground;

  /// The initials' type role.
  final TextStyle initials;

  /// The disc's diameter.
  final double diameter;

  /// The style for [size] in [ui].
  static UiAvatarStyle resolve(UiThemeData ui, UiAvatarSize size) =>
      UiAvatarStyle(
        // 10 section 4.5 asks for `ink` at 8 percent. `hoverOpacity` is the
        // token carrying 8 percent in light and the dark column's
        // counterpart, so the disc tracks the mode the way every other
        // overlay in the system does rather than pinning a literal.
        fill: ui.color.stateLayer(ui.color.hoverOpacity),
        foreground: ui.color.inkSecondary,
        initials: ui.type.label,
        diameter: size.diameter,
      );

  /// The initials of [name]: the first character of its first word, and of
  /// its last word where there is more than one.
  ///
  /// The characters are taken as the person wrote them and never upper
  /// cased. 09 section 11 rejects upper case everywhere but the `unit` role,
  /// and a name in a script with no case has no upper form to take.
  static String initialsOf(String name) {
    final List<String> words = name
        .split(RegExp(r'\s+'))
        .where((String word) => word.isNotEmpty)
        .toList(growable: false);
    if (words.isEmpty) return '';
    final String first = words.first.characters.first;
    if (words.length == 1) return first;
    return '$first${words.last.characters.first}';
  }
}

/// A person, as a disc of initials or as their photograph.
///
/// [name] is required and is the whole of the semantics: an avatar is an
/// image with no text of its own, and two people whose initials collide are
/// one glyph apart without it (10 section 11).
class UiAvatar extends StatelessWidget {
  /// The disc for [name].
  const UiAvatar({
    super.key,
    required this.name,
    this.image,
    this.size = UiAvatarSize.medium,
  });

  /// Whose disc this is. Read aloud in full.
  final String name;

  /// Their photograph. The initials are drawn when this is null and when the
  /// image cannot be decoded, because a person who has no photograph is a
  /// fact about the record rather than a hole in the row.
  final ImageProvider? image;

  /// The disc's diameter.
  final UiAvatarSize size;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final UiAvatarStyle style = UiAvatarStyle.resolve(ui, size);
    final ImageProvider? provider = image;
    final Widget initials = DecoratedBox(
      decoration: ShapeDecoration(
        shape: const StadiumBorder(),
        color: style.fill,
      ),
      child: Center(
        child: UiLabel(
          UiAvatarStyle.initialsOf(name),
          style: style.initials.copyWith(color: style.foreground),
        ),
      ),
    );
    return Semantics(
      image: true,
      label: name,
      excludeSemantics: true,
      child: SizedBox.square(
        dimension: style.diameter,
        child: provider == null
            ? initials
            : ClipOval(
                child: Image(
                  image: provider,
                  fit: BoxFit.cover,
                  width: style.diameter,
                  height: style.diameter,
                  gaplessPlayback: true,
                  errorBuilder:
                      (BuildContext context, Object error, StackTrace? stack) =>
                          initials,
                ),
              ),
      ),
    );
  }
}
