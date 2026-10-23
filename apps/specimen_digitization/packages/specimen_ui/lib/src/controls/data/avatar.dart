/// The person disc (10 section 4.5, `UiAvatar`).
library;

import 'package:flutter/widgets.dart';

import '../../foundation/theme.dart';
import '../../foundation/icons.dart';
import '../../primitives/label.dart';
import '../actions/icon_button.dart';

/// Identity diameters from compact supporting rows through profile headers.
enum UiAvatarSize {
  /// 24. Compact supporting identity.
  extraSmall(24),

  /// 32. Inside a row, beside a decision.
  small(32),

  /// 40. In the account menu and at the head of a history entry.
  medium(40),

  /// 48. Leading identity in a card.
  large(48),

  /// 56. A prominent identity.
  extraLarge(56),

  /// 64. Identity in a detail header.
  doubleExtraLarge(64),

  /// 96. A profile photograph.
  profile(96),

  /// 160. A large profile photograph.
  profileLarge(160);

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
        initials: size.diameter >= UiAvatarSize.profile.diameter
            ? ui.type.headline
            : size.diameter >= UiAvatarSize.doubleExtraLarge.diameter
            ? ui.type.title
            : ui.type.label,
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
    this.status = UiAvatarStatus.none,
    this.statusLabel,
    this.badge,
  });

  /// Whose disc this is. Read aloud in full.
  final String name;

  /// Their photograph. The initials are drawn when this is null and when the
  /// image cannot be decoded, because a person who has no photograph is a
  /// fact about the record rather than a hole in the row.
  final ImageProvider? image;

  /// The disc's diameter.
  final UiAvatarSize size;

  /// Caller-reported status; never inferred from a photo or name.
  final UiAvatarStatus status;

  /// The localized meaning of the status or decorative identity badge.
  final String? statusLabel;

  /// Decorative company or role badge. [statusLabel] provides its meaning.
  final Widget? badge;

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
        child: name.trim().isEmpty
            ? UiIcon(
                UiIcons.reviewer,
                color: style.foreground,
                size: UiIconSize.action,
              )
            : UiLabel(
                UiAvatarStyle.initialsOf(name),
                style: style.initials.copyWith(color: style.foreground),
              ),
      ),
    );
    return Semantics(
      image: true,
      label: [
        name,
        if (statusLabel != null)
          statusLabel!
        else if (status != UiAvatarStatus.none)
          status.name,
      ].join(', '),
      excludeSemantics: true,
      child: Stack(
        clipBehavior: Clip.none,
        children: <Widget>[
          SizedBox.square(
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
                          (
                            BuildContext context,
                            Object error,
                            StackTrace? stack,
                          ) => initials,
                    ),
                  ),
          ),
          if (badge != null || status != UiAvatarStatus.none)
            PositionedDirectional(
              end: 0,
              bottom: 0,
              child: Container(
                width: size.diameter / 3,
                height: size.diameter / 3,
                decoration: BoxDecoration(
                  color: status == UiAvatarStatus.online
                      ? ui.color.status.cleared.content
                      : status == UiAvatarStatus.verified
                      ? ui.brand.secondary.content
                      : ui.color.inkSecondary,
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: ui.color.paper,
                    width: ui.shape.stroke.emphasis,
                  ),
                ),
                child:
                    badge ??
                    (status == UiAvatarStatus.verified
                        ? FittedBox(
                            child: UiIcon(
                              UiIcons.check,
                              color: ui.color.paper,
                              size: UiIconSize.small,
                            ),
                          )
                        : null),
              ),
            ),
        ],
      ),
    );
  }
}

/// Identity decoration; consumers supply the authoritative status.
enum UiAvatarStatus {
  /// No reported status.
  none,

  /// Reported online presence.
  online,

  /// Reported offline presence.
  offline,

  /// An explicitly verified identity.
  verified,
}

/// Identity data for an avatar group.
@immutable
class UiAvatarPerson {
  /// Creates the component with explicit caller-owned configuration.
  const UiAvatarPerson({required this.name, this.image});

  /// The complete human-readable identity.
  final String name;

  /// The optional photograph; absent or failed images use initials.
  final ImageProvider? image;
}

/// An overlapping identity group with named overflow and an optional add action.
///
/// The complete membership is announced once, even when only a subset fits.
/// The add control has its own 48 dp target and accessible name.
class UiAvatarGroup extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiAvatarGroup({
    super.key,
    required this.label,
    required this.people,
    this.maxVisible = 5,
    this.size = UiAvatarSize.medium,
    this.onAdd,
    this.addLabel = 'Add person',
  }) : assert(maxVisible > 0);

  /// The visible and accessible name of the control.
  final String label;

  /// The people represented, including members hidden by available space.
  final List<UiAvatarPerson> people;

  /// The maximum number of individual avatars before the overflow count.
  final int maxVisible;

  /// The visual size; interactive targets retain their accessible minimum.
  final UiAvatarSize size;

  /// The optional separate action for adding a person.
  final VoidCallback? onAdd;

  /// The accessible name of the add-person action.
  final String addLabel;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    return LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.hasBoundedWidth
            ? constraints.maxWidth -
                  (onAdd == null ? 0 : ui.space.targetMin + ui.space.s2)
            : size.diameter * (maxVisible + 1);
        final step = size.diameter * .75;
        final capacity = ((available - size.diameter) / step).floor() + 1;
        final fit = capacity.clamp(1, maxVisible + 1);
        final visibleLimit = people.length > fit ? fit - 1 : fit;
        final count = people.length.clamp(0, maxVisible.clamp(0, visibleLimit));
        final hidden = people.length - count;
        final slots = count + (hidden > 0 ? 1 : 0);
        final group = Semantics(
          label: '$label: ${people.map((p) => p.name).join(', ')}',
          excludeSemantics: true,
          child: SizedBox(
            width: slots == 0 ? 0 : size.diameter + (slots - 1) * step,
            height: size.diameter,
            child: Stack(
              children: <Widget>[
                for (int i = 0; i < slots; i++)
                  PositionedDirectional(
                    start: i * step,
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        border: Border.all(
                          color: ui.color.paper,
                          width: ui.shape.stroke.emphasis,
                        ),
                      ),
                      child: i < count
                          ? UiAvatar(
                              name: people[i].name,
                              image: people[i].image,
                              size: size,
                            )
                          : SizedBox.square(
                              dimension: size.diameter,
                              child: DecoratedBox(
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: ui.color.matte,
                                ),
                                child: Center(
                                  child: Text('+$hidden', style: ui.type.label),
                                ),
                              ),
                            ),
                    ),
                  ),
              ],
            ),
          ),
        );
        return Wrap(
          spacing: ui.space.s2,
          runSpacing: ui.space.s2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            group,
            if (onAdd != null)
              UiIconButton(
                icon: UiIcons.add,
                semanticsLabel: addLabel,
                onPressed: onAdd,
              ),
          ],
        );
      },
    );
  }
}

/// A full identity label and supporting detail beside its photograph.
class UiAvatarLabel extends StatelessWidget {
  /// Creates the component with explicit caller-owned configuration.
  const UiAvatarLabel({
    super.key,
    required this.name,
    this.supporting,
    this.image,
    this.status = UiAvatarStatus.none,
    this.size = UiAvatarSize.medium,
  });

  /// The complete human-readable identity.
  final String name;

  /// The optional explanatory text accompanying the primary label.
  final String? supporting;

  /// The optional photograph; absent or failed images use initials.
  final ImageProvider? image;

  /// The host-reported semantic state.
  final UiAvatarStatus status;

  /// The visual size; interactive targets retain their accessible minimum.
  final UiAvatarSize size;

  @override
  Widget build(BuildContext context) => MergeSemantics(
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        ExcludeSemantics(
          child: UiAvatar(name: name, image: image, size: size, status: status),
        ),
        SizedBox(width: context.ui.space.s3),
        Flexible(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(name, style: context.ui.type.label),
              if (supporting != null)
                Text(supporting!, style: context.ui.type.bodySmall),
              if (status != UiAvatarStatus.none)
                Text(status.name, style: context.ui.type.bodySmall),
            ],
          ),
        ),
      ],
    ),
  );
}
