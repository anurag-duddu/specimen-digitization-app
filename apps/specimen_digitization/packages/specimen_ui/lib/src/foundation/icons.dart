/// The icon registry (09 section 7; build plan appendix A).
///
/// Every glyph in the product enters the tree through [UiIcons], so one
/// meaning has one icon everywhere. A screen never names a Phosphor glyph.
/// Two glyphs for one meaning is a defect, and `icons_unique` is the gate.
library;

import 'package:flutter/widgets.dart';
import 'package:phosphor_flutter/phosphor_flutter.dart';

/// The font family a Phosphor weight resolves to.
///
/// Public so a test can load the faces: a golden of the icon page that draws
/// a box instead of a glyph reviews nothing, and "two glyphs for one meaning"
/// is exactly what that page exists to make visible.
abstract final class PhosphorFonts {
  /// The package the faces ship in.
  static const String package = 'phosphor_flutter';

  /// The family and asset of each weight the product draws.
  static const Map<String, String> families = <String, String>{
    'PhosphorRegular': 'lib/fonts/Phosphor.ttf',
    'PhosphorFill': 'lib/fonts/Phosphor-Fill.ttf',
    'PhosphorLight': 'lib/fonts/Phosphor-Light.ttf',
  };

  /// The bundle path of [asset] inside the Phosphor package.
  static String bundlePath(String asset) => 'packages/$package/$asset';

  /// The family name Flutter resolves a Phosphor face under.
  ///
  /// `PhosphorIconData` sets `fontPackage`, so the family the engine looks
  /// for carries the package prefix. A `FontLoader` registered under the bare
  /// name loads a face nothing then asks for, and every glyph renders as a
  /// box.
  static String prefixed(String family) => 'packages/$package/$family';
}

/// The Phosphor weights this product uses.
///
/// `thin`, `bold` and `duotone` are not used; `bold` appears only inside the
/// mark, which is an asset rather than a glyph.
enum UiIconWeight {
  /// Every interface glyph by default: actions, navigation, chips, rows.
  regular,

  /// A settled disposition and the current navigation destination.
  fill,

  /// Decorative glyphs at 40 dp and above: empty states, the help screen.
  light,
}

/// One registry entry: a glyph, the weight it is drawn at, and the fill form
/// where 09 names one.
@immutable
class IconSpec {
  /// Binds one meaning to its glyph.
  const IconSpec(this.glyph, {this.weight = UiIconWeight.regular, this.filled});

  /// The regular form. Also the light form for a decorative glyph.
  final IconData glyph;

  /// The weight this entry is drawn at unless a call site asks for the
  /// current form.
  final UiIconWeight weight;

  /// The fill form, for a settled disposition and for a destination that can
  /// be current. Null everywhere else.
  final IconData? filled;

  /// The glyph to draw. [current] selects the fill form for a destination
  /// the reviewer is on.
  IconData resolve({bool current = false}) {
    if (current || weight == UiIconWeight.fill) return filled ?? glyph;
    return glyph;
  }

  /// The glyph this entry draws with no call-site override. The uniqueness
  /// gate compares these.
  IconData get defaultGlyph => resolve();
}

/// Every meaning the product can draw.
abstract final class UiIcons {
  // Navigation destinations. Regular, and fill when current.

  /// The queue destination; also the empty-queue glyph.
  static const IconSpec queue = IconSpec(
    PhosphorIconsRegular.tray,
    filled: PhosphorIconsFill.tray,
  );

  /// The intake destination.
  static const IconSpec intake = IconSpec(
    PhosphorIconsRegular.plusSquare,
    filled: PhosphorIconsFill.plusSquare,
  );

  /// The registered sources destination.
  static const IconSpec sources = IconSpec(
    PhosphorIconsRegular.folderOpen,
    filled: PhosphorIconsFill.folderOpen,
  );

  // Settled dispositions. Drawn filled, per the v1 fill rule.

  /// Cleared.
  static const IconSpec cleared = IconSpec(
    PhosphorIconsRegular.checkCircle,
    weight: UiIconWeight.fill,
    filled: PhosphorIconsFill.checkCircle,
  );

  /// Needs human review.
  static const IconSpec needsReview = IconSpec(
    PhosphorIconsRegular.flag,
    weight: UiIconWeight.fill,
    filled: PhosphorIconsFill.flag,
  );

  /// Deferred.
  static const IconSpec deferred = IconSpec(
    PhosphorIconsRegular.pauseCircle,
    weight: UiIconWeight.fill,
    filled: PhosphorIconsFill.pauseCircle,
  );

  // Operational and evidentiary states.

  /// Processing. Paired with the progress ring when determinate.
  static const IconSpec processing = IconSpec(PhosphorIconsRegular.spinnerGap);

  /// Processing blocked. Operational, not evidentiary.
  static const IconSpec blocked = IconSpec(PhosphorIconsRegular.prohibit);

  /// State unknown, and the unknown abstention. One key for both.
  static const IconSpec unknown = IconSpec(PhosphorIconsRegular.question);

  /// A model produced this reading.
  static const IconSpec modelReading = IconSpec(PhosphorIconsRegular.cpu);

  /// A reviewer decided this.
  static const IconSpec reviewer = IconSpec(PhosphorIconsRegular.user);

  /// An external authority matched this value.
  static const IconSpec authority = IconSpec(PhosphorIconsRegular.bookOpenText);

  /// The low risk band.
  static const IconSpec riskLow = IconSpec(PhosphorIconsRegular.cellSignalLow);

  /// The middle risk band.
  static const IconSpec riskMedium = IconSpec(
    PhosphorIconsRegular.cellSignalMedium,
  );

  /// The top risk band.
  static const IconSpec riskHigh = IconSpec(
    PhosphorIconsRegular.cellSignalFull,
  );

  /// The test environment banner.
  static const IconSpec synthetic = IconSpec(PhosphorIconsRegular.flask);

  // Abstentions. A value that is absent, in the slot the value would occupy.

  /// Unreadable; also hide a value.
  static const IconSpec unreadable = IconSpec(PhosphorIconsRegular.eyeSlash);

  /// Not present.
  static const IconSpec notPresent = IconSpec(PhosphorIconsRegular.minus);

  /// Not measured.
  static const IconSpec unmeasured = IconSpec(
    PhosphorIconsRegular.circleDashed,
  );

  // Shell and account.

  /// Help and the glossary.
  static const IconSpec help = IconSpec(PhosphorIconsRegular.lifebuoy);

  /// The account menu.
  static const IconSpec account = IconSpec(PhosphorIconsRegular.userCircle);

  /// Sign out.
  static const IconSpec signOut = IconSpec(PhosphorIconsRegular.signOut);

  /// Settings.
  static const IconSpec settings = IconSpec(PhosphorIconsRegular.gearSix);

  /// The shortcut map.
  static const IconSpec keyboard = IconSpec(PhosphorIconsRegular.keyboard);

  // Actions.

  /// Reload a list. Distinct from [retry], which restarts processing.
  static const IconSpec reload = IconSpec(PhosphorIconsRegular.arrowClockwise);

  /// Retry processing from a checkpoint.
  static const IconSpec retry = IconSpec(
    PhosphorIconsRegular.arrowCounterClockwise,
  );

  /// Rotate the view of the photograph. The photograph itself never turns.
  static const IconSpec rotateView = IconSpec(
    PhosphorIconsRegular.arrowsClockwise,
  );

  /// Filter the queue.
  static const IconSpec filter = IconSpec(PhosphorIconsRegular.funnel);

  /// Search.
  static const IconSpec search = IconSpec(PhosphorIconsRegular.magnifyingGlass);

  /// Correct label regions.
  static const IconSpec correctRegions = IconSpec(PhosphorIconsRegular.crop);

  /// Copy a value.
  static const IconSpec copy = IconSpec(PhosphorIconsRegular.copy);

  /// Back.
  static const IconSpec back = IconSpec(PhosphorIconsRegular.arrowLeft);

  /// Close.
  static const IconSpec close = IconSpec(PhosphorIconsRegular.x);

  /// A closed disclosure; also the select caret.
  static const IconSpec expand = IconSpec(PhosphorIconsRegular.caretDown);

  /// An open disclosure.
  static const IconSpec collapse = IconSpec(PhosphorIconsRegular.caretUp);

  /// The next record; also a row affordance.
  static const IconSpec next = IconSpec(PhosphorIconsRegular.caretRight);

  /// The previous record.
  static const IconSpec previous = IconSpec(PhosphorIconsRegular.caretLeft);

  /// The confirmation mark inside a toggle or a menu.
  static const IconSpec check = IconSpec(PhosphorIconsRegular.check);

  /// Edit with a reason.
  static const IconSpec editReason = IconSpec(PhosphorIconsRegular.notePencil);

  /// Edit.
  static const IconSpec edit = IconSpec(PhosphorIconsRegular.pencilSimple);

  /// An inline error.
  static const IconSpec error = IconSpec(PhosphorIconsRegular.warningCircle);

  /// Supporting information.
  static const IconSpec info = IconSpec(PhosphorIconsRegular.info);

  /// The whole-image region.
  static const IconSpec wholeImage = IconSpec(PhosphorIconsRegular.cornersOut);

  /// Decision history.
  static const IconSpec history = IconSpec(
    PhosphorIconsRegular.clockCounterClockwise,
  );

  /// Locked.
  static const IconSpec locked = IconSpec(PhosphorIconsRegular.lock);

  /// Unlocked.
  static const IconSpec unlocked = IconSpec(PhosphorIconsRegular.lockOpen);

  /// Enter full screen.
  static const IconSpec enterFullscreen = IconSpec(
    PhosphorIconsRegular.arrowsOutSimple,
  );

  /// Leave full screen.
  static const IconSpec exitFullscreen = IconSpec(
    PhosphorIconsRegular.arrowsInSimple,
  );

  /// Fit the photograph to the view.
  static const IconSpec fitToView = IconSpec(PhosphorIconsRegular.frameCorners);

  /// Zoom in.
  static const IconSpec zoomIn = IconSpec(
    PhosphorIconsRegular.magnifyingGlassPlus,
  );

  /// Zoom out.
  static const IconSpec zoomOut = IconSpec(
    PhosphorIconsRegular.magnifyingGlassMinus,
  );

  /// Take a photograph.
  static const IconSpec camera = IconSpec(PhosphorIconsRegular.camera);

  /// Waiting time and timestamps.
  static const IconSpec time = IconSpec(PhosphorIconsRegular.clock);

  /// Provenance.
  static const IconSpec provenance = IconSpec(
    PhosphorIconsRegular.treeStructure,
  );

  /// Add.
  static const IconSpec add = IconSpec(PhosphorIconsRegular.plus);

  /// A superseded run.
  static const IconSpec superseded = IconSpec(PhosphorIconsRegular.arrowsSplit);

  /// A record.
  static const IconSpec record = IconSpec(PhosphorIconsRegular.article);

  /// A collection.
  static const IconSpec collection = IconSpec(PhosphorIconsRegular.microscope);

  /// Save a filter.
  static const IconSpec saveFilter = IconSpec(
    PhosphorIconsRegular.bookmarkSimple,
  );

  /// An unchecked box. Drawn only inside the checkbox control.
  static const IconSpec unselected = IconSpec(PhosphorIconsRegular.square);

  /// Import from a registered source.
  static const IconSpec sourceImport = IconSpec(
    PhosphorIconsRegular.cloudArrowDown,
  );

  /// Upload to the collection.
  static const IconSpec cloudUpload = IconSpec(
    PhosphorIconsRegular.cloudArrowUp,
  );

  /// A date range.
  static const IconSpec dateRange = IconSpec(
    PhosphorIconsRegular.calendarBlank,
  );

  /// Remove.
  static const IconSpec remove = IconSpec(PhosphorIconsRegular.trash);

  /// Download.
  static const IconSpec download = IconSpec(
    PhosphorIconsRegular.downloadSimple,
  );

  /// The capture checklist.
  static const IconSpec checklist = IconSpec(PhosphorIconsRegular.listChecks);

  /// A registered source.
  static const IconSpec source = IconSpec(PhosphorIconsRegular.folder);

  /// A thumbnail placeholder.
  static const IconSpec image = IconSpec(PhosphorIconsRegular.image);

  /// Add to a batch.
  static const IconSpec addToBatch = IconSpec(PhosphorIconsRegular.stackPlus);

  /// The overflow menu.
  static const IconSpec more = IconSpec(PhosphorIconsRegular.dotsThreeVertical);

  /// Pending.
  static const IconSpec pending = IconSpec(
    PhosphorIconsRegular.dotsThreeCircle,
  );

  /// Save.
  static const IconSpec save = IconSpec(PhosphorIconsRegular.floppyDisk);

  /// The empty search state. Drawn light at 40 dp.
  static const IconSpec noResults = IconSpec(
    PhosphorIconsLight.binoculars,
    weight: UiIconWeight.light,
  );

  /// Select every row.
  static const IconSpec selectAll = IconSpec(PhosphorIconsRegular.selectionAll);

  /// Cancel processing.
  static const IconSpec stop = IconSpec(PhosphorIconsRegular.stopCircle);

  /// An upload or source synchronisation stopped.
  static const IconSpec syncProblem = IconSpec(
    PhosphorIconsRegular.cloudWarning,
  );

  /// Undo.
  static const IconSpec undo = IconSpec(PhosphorIconsRegular.arrowUUpLeft);

  /// Upload a file.
  static const IconSpec uploadFile = IconSpec(PhosphorIconsRegular.fileArrowUp);

  /// Reveal a value.
  static const IconSpec show = IconSpec(PhosphorIconsRegular.eye);

  /// A declared script.
  static const IconSpec script = IconSpec(PhosphorIconsRegular.textAa);

  /// A declared language.
  static const IconSpec language = IconSpec(PhosphorIconsRegular.translate);

  /// The registry key of the pin mark.
  ///
  /// The mark is an asset, not a Phosphor glyph (09 section 9), so it has no
  /// [IconSpec] and is absent from [all]. Slot E6 draws it. It is named here
  /// because [fromSymbolName] has to resolve the v1 sign-in glyph to
  /// something, and resolving it to a borrowed glyph would be exactly the
  /// "two meanings, one glyph" defect the registry exists to prevent.
  static const String markKey = 'mark';

  /// Every entry, by registry key.
  static const Map<String, IconSpec> byKey = <String, IconSpec>{
    'queue': queue,
    'intake': intake,
    'sources': sources,
    'cleared': cleared,
    'needsReview': needsReview,
    'deferred': deferred,
    'processing': processing,
    'blocked': blocked,
    'unknown': unknown,
    'modelReading': modelReading,
    'reviewer': reviewer,
    'authority': authority,
    'riskLow': riskLow,
    'riskMedium': riskMedium,
    'riskHigh': riskHigh,
    'synthetic': synthetic,
    'unreadable': unreadable,
    'notPresent': notPresent,
    'unmeasured': unmeasured,
    'help': help,
    'account': account,
    'signOut': signOut,
    'settings': settings,
    'keyboard': keyboard,
    'reload': reload,
    'retry': retry,
    'rotateView': rotateView,
    'filter': filter,
    'search': search,
    'correctRegions': correctRegions,
    'copy': copy,
    'back': back,
    'close': close,
    'expand': expand,
    'collapse': collapse,
    'next': next,
    'previous': previous,
    'check': check,
    'editReason': editReason,
    'edit': edit,
    'error': error,
    'info': info,
    'wholeImage': wholeImage,
    'history': history,
    'locked': locked,
    'unlocked': unlocked,
    'enterFullscreen': enterFullscreen,
    'exitFullscreen': exitFullscreen,
    'fitToView': fitToView,
    'zoomIn': zoomIn,
    'zoomOut': zoomOut,
    'camera': camera,
    'time': time,
    'provenance': provenance,
    'add': add,
    'superseded': superseded,
    'record': record,
    'collection': collection,
    'saveFilter': saveFilter,
    'unselected': unselected,
    'sourceImport': sourceImport,
    'cloudUpload': cloudUpload,
    'dateRange': dateRange,
    'remove': remove,
    'download': download,
    'checklist': checklist,
    'source': source,
    'image': image,
    'addToBatch': addToBatch,
    'more': more,
    'pending': pending,
    'save': save,
    'noResults': noResults,
    'selectAll': selectAll,
    'stop': stop,
    'syncProblem': syncProblem,
    'undo': undo,
    'uploadFile': uploadFile,
    'show': show,
    'script': script,
    'language': language,
  };

  /// Every spec, for the uniqueness gate.
  static List<IconSpec> get all => byKey.values.toList(growable: false);

  /// The v1 Material glyph names, mapped to registry keys.
  ///
  /// This is the codemod's source of truth for the later waves: a screen agent
  /// replacing `Symbols.inventory_2` looks the name up here rather than
  /// choosing a Phosphor glyph, which is what keeps one meaning on one icon.
  /// Transcribed from build plan appendix A.
  static const Map<String, String> symbolNames = <String, String>{
    'Symbols.inventory_2': 'queue',
    'Symbols.inbox': 'queue',
    'Symbols.check_circle': 'cleared',
    'Symbols.close': 'close',
    'Symbols.chevron_right': 'next',
    'Symbols.chevron_left': 'previous',
    'Symbols.hide_source': 'unmeasured',
    'Symbols.refresh': 'reload',
    'Symbols.add_photo_alternate': 'intake',
    'Symbols.check': 'check',
    'Symbols.content_copy': 'copy',
    'Symbols.edit_note': 'editReason',
    'Symbols.error': 'error',
    'Symbols.expand_more': 'expand',
    'Symbols.arrow_drop_down': 'expand',
    'Symbols.expand_less': 'collapse',
    'Symbols.autorenew': 'processing',
    'Symbols.block': 'blocked',
    'Symbols.crop_free': 'wholeImage',
    'Symbols.flag': 'needsReview',
    'Symbols.help': 'help',
    'Symbols.history': 'history',
    'Symbols.horizontal_rule': 'notPresent',
    'Symbols.info': 'info',
    'Symbols.lock': 'locked',
    'Symbols.lock_open': 'unlocked',
    'Symbols.logout': 'signOut',
    'Symbols.memory': 'modelReading',
    'Symbols.menu_book': 'authority',
    'Symbols.open_in_full': 'enterFullscreen',
    'Symbols.close_fullscreen': 'exitFullscreen',
    'Symbols.photo_camera': 'camera',
    'Symbols.rotate_right': 'rotateView',
    'Symbols.schedule': 'time',
    'Symbols.account_tree': 'provenance',
    'Symbols.add': 'add',
    'Symbols.alt_route': 'superseded',
    'Symbols.arrow_back': 'back',
    'Symbols.article': 'record',
    'Symbols.biotech': 'collection',
    'Symbols.bookmark_add': 'saveFilter',
    'Symbols.check_box_outline_blank': 'unselected',
    'Symbols.cloud_sync': 'sourceImport',
    'Symbols.cloud_upload': 'cloudUpload',
    'Symbols.crop': 'correctRegions',
    'Symbols.date_range': 'dateRange',
    'Symbols.delete': 'remove',
    'Symbols.download': 'download',
    'Symbols.edit': 'edit',
    'Symbols.fact_check': 'checklist',
    'Symbols.filter_list': 'filter',
    'Symbols.fit_screen': 'fitToView',
    'Symbols.folder': 'source',
    'Symbols.image': 'image',
    'Symbols.keyboard': 'keyboard',
    'Symbols.library_add': 'addToBatch',
    'Symbols.more_vert': 'more',
    'Symbols.pause_circle': 'deferred',
    'Symbols.pending': 'pending',
    'Symbols.person': 'reviewer',
    'Symbols.replay': 'retry',
    'Symbols.save': 'save',
    'Symbols.science': 'synthetic',
    'Symbols.search': 'search',
    'Symbols.search_off': 'noResults',
    'Symbols.select_all': 'selectAll',
    'Symbols.settings': 'settings',
    'Symbols.stop_circle': 'stop',
    'Symbols.sync_problem': 'syncProblem',
    'Symbols.undo': 'undo',
    'Symbols.upload_file': 'uploadFile',
    'Symbols.visibility': 'show',
    'Symbols.visibility_off': 'unreadable',
    'Symbols.zoom_in': 'zoomIn',
    'Symbols.zoom_out': 'zoomOut',
    'Symbols.signal_cellular_alt_1_bar': 'riskLow',
    'Symbols.signal_cellular_alt_2_bar': 'riskMedium',
    'Symbols.signal_cellular_alt': 'riskHigh',
    'Icons.abc': 'script',
    'Icons.biotech_outlined': markKey,
    'Icons.expand_less': 'collapse',
    'Icons.expand_more': 'expand',
    'Icons.translate': 'language',
    'Icons.visibility': 'show',
    'Icons.visibility_off': 'unreadable',
  };

  /// The registry key for a v1 Material glyph name, or null when the name is
  /// not one this product used.
  ///
  /// Accepts the name with or without its class prefix, so both
  /// `Symbols.inventory_2` and `inventory_2` resolve.
  static String? fromSymbolName(String name) {
    final String trimmed = name.trim();
    final String? direct = symbolNames[trimmed];
    if (direct != null) return direct;
    if (!trimmed.contains('.')) {
      return symbolNames['Symbols.$trimmed'] ?? symbolNames['Icons.$trimmed'];
    }
    return null;
  }

  /// The spec for a registry key, or null when the key names the mark or is
  /// not in the registry.
  static IconSpec? spec(String key) => byKey[key];
}

/// Draws one registry entry.
///
/// The colour follows the surrounding text, so a glyph beside a label is
/// always the same colour as the label without a call site naming either.
class UiIcon extends StatelessWidget {
  /// Draws [spec] at [size].
  const UiIcon(
    this.spec, {
    super.key,
    this.size = UiIconSize.action,
    this.current = false,
    this.color,
    this.semanticLabel,
  });

  /// Which meaning to draw.
  final IconSpec spec;

  /// One of the four sizes in 09 section 7.
  final UiIconSize size;

  /// True for the destination the reviewer is on, which selects the fill
  /// form where the entry has one.
  final bool current;

  /// Overrides the ambient text colour. Used by a control that paints its own
  /// foreground from a state.
  final Color? color;

  /// The label a screen reader reads. Required wherever the glyph is the only
  /// content of a control; the control sets it, not this widget.
  final String? semanticLabel;

  @override
  Widget build(BuildContext context) => Icon(
    spec.resolve(current: current),
    size: size.dimension,
    color: color ?? DefaultTextStyle.of(context).style.color,
    semanticLabel: semanticLabel,
  );
}

/// The four glyph sizes (09 section 7).
enum UiIconSize {
  /// Inline with `label.small`.
  small(16),

  /// Inline with `body`.
  inline(20),

  /// Actions, rows, navigation.
  action(24),

  /// Empty states.
  display(40);

  const UiIconSize(this.dimension);

  /// The size in logical pixels.
  final double dimension;
}
