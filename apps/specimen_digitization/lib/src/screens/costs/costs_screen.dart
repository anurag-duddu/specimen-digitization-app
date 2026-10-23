/// What the organization's work costs, month by month (screen blueprints,
/// section 15).
///
/// One vertical scroll: the month, the organization's figures and limit, each
/// collection, the month's cost by stage and by model, and how fresh the
/// figures are. The screen shows what the server's cost meter reports and adds
/// nothing up: a figure the meter did not record is said in words, never drawn
/// as zero (00 principle 2).
///
/// Only an administrator reaches it, and the route and the account menu both
/// ask `costOrganizationFor` before they offer or draw it, so the requests
/// here are only ever made for one.
library;

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../../costs.dart';
import '../../models.dart';
import '../../money.dart';
import '../../vocabulary.dart';
import '../../widgets/adaptive_form.dart';
import '../../widgets/loading_announcement.dart';
import '../../widgets/queue_row.dart' show absoluteTime;
import 'cost_limit_form.dart';

/// The words of the costs screen, in one place so a test names them rather
/// than repeating them.
abstract final class CostsScreenCopy {
  /// The screen's name, in the top bar.
  static const String title = 'Costs';

  // The month.
  static const String monthLabel = 'Month';
  static const String monthPlaceholder = 'Choose a month';
  static const String monthHelp = 'Months are counted in UTC.';

  /// What the load announces, with the month in it.
  static String loadingThing(String month) => 'costs for $month';

  // A load that did not work.
  static const String notLoadedTitle = 'Costs not loaded';
  static const String retry = 'Retry';
  static const String unavailableTitle = 'Costs not available';
  static const String unavailableBody =
      'This server does not track costs yet. Ask the people who run it to '
      'turn them on.';
  static const String unavailableBuildBody =
      'This build of the app cannot read costs. Use the current release.';
  static const String forbiddenTitle = 'Costs are for administrators';
  static const String forbiddenBody =
      'Your account is not an administrator of this organization. Ask an '
      'administrator for the figures.';

  /// The server's own code for a deployment with no cost meter.
  static const String unavailableCode = 'cost_meter_unavailable';

  // The organization.
  static const String organizationHeading = 'Organization';
  static String costLabel(String month) => 'Cost in $month';
  static const String costFooter = "After Google's free allowance.";
  static const String heldLabel = 'Held, cost unknown';
  static const String heldFooter =
      'The part held for calls whose cost is unknown.';
  static const String heldNoneFooter =
      'Nothing is held for calls whose cost is unknown.';
  static const String listCostLabel = 'Before free allowance';
  static const String listCostFooter =
      "The same costs before Google's free allowance.";

  /// What a slice with nothing recorded says in place of an amount.
  static const String noCosts = 'No costs recorded';
  static String noCostsBody(String month) =>
      'No costs were counted for the organization in $month.';

  // Limits.
  static const String organizationLimitHeading = 'Organization limit';
  static const String organizationSubject = 'Organization';
  static const String noOrganizationLimit =
      'No monthly limit is set for the organization.';
  static const String setLimit = 'Set limit';
  static const String changeLimit = 'Change limit';
  static const String noLimit = 'No monthly limit';
  static const String limitReachedValue = 'None left';

  /// What the report says when it could not read the limits. Its limits are
  /// all null then, and null is not "no limit", so nothing here says none is
  /// set and nothing offers to set one over a limit that cannot be seen.
  static const String limitsUnreadable =
      'The monthly limits could not be read.';
  static const String rowLimitUnreadable = 'Limit could not be read';

  /// The label over what a limit has left, for the month the limit counts.
  static String leftLabel(String month) =>
      month.isEmpty ? 'Left this month' : 'Left in ${costMonthLabel(month)}';

  /// The line under it: what was used, of what, and when.
  static String limitFooter(CostLimit limit) {
    final String of =
        '${formatMicros(limit.spentMicros)} spent of '
        '${formatMicros(limit.monthlyMicros)}';
    return limit.month.isEmpty
        ? '$of.'
        : '$of in ${costMonthLabel(limit.month)}.';
  }

  /// A collection's limit on its row.
  static String rowLimit(CostLimit? limit) {
    if (limit == null) return noLimit;
    return limit.reached
        ? 'Limit of ${formatMicros(limit.monthlyMicros)} reached'
        : '${formatMicros(limit.remainingMicros)} left of '
              '${formatMicros(limit.monthlyMicros)}';
  }

  // Collections.
  static const String collectionsHeading = 'Collections';
  static const String noCollections = 'No collections to show.';

  /// What a collection the server no longer lists is called. Its costs still
  /// count, under no name, and its id is not a name.
  static const String collectionNotListed = 'Collection no longer listed';
  static const String includingSubCollections = 'including sub-collections';

  // Stages and models.
  static const String stagesHeading = 'Cost by stage';
  static const String modelsHeading = 'Cost by model';

  /// A count of metered calls.
  static String entries(int count) =>
      count == 1 ? '1 entry' : '${formatCount(count)} entries';

  /// What is held, on a row that holds something.
  static String held(int micros) => '${formatMicros(micros)} held';

  // How fresh the figures are.
  static const String figuresHeading = 'Figures';
  static String updated(String when) => 'Updated $when.';
  static const String updatedUnknown = 'Update time not recorded.';
  static String countedThrough(String day) =>
      'Shared Google costs are counted through $day, a billing day in '
      'Pacific time.';
  static String countingStatus(String status) =>
      'Shared Google costs: ${vocabularyLabel(status)}.';
  static const String behindTitle = 'Shared Google costs are behind.';

  /// What "behind" means, and how far the meter has got when it says.
  static String behindDetail(String? day) =>
      'More than two complete billing days behind.'
      '${day == null ? '' : ' Counted through $day, a billing day in Pacific time.'}';
  static const String neverRunTitle =
      'No shared Google costs have been counted.';
  static const String refreshLabel = 'Update figures';
  static const String refreshBusy = 'Updating…';
  static const String refreshStarted =
      'Update requested. The figures update within minutes.';
  // Said when the server answers `started: false`: no worker job is
  // configured, or the start failed. All that is known is that nothing was
  // started, so nothing is promised.
  static const String refreshNotStarted =
      'No update was started. Try again later.';
  static const String refreshFailed =
      'The update did not start. Retry in a moment.';
}

/// Where the person pressed "Update figures": the band above the figures, or
/// the Figures section at the end of the page. The outcome is shown beside the
/// control that was used, so a phone does not leave the person looking at a
/// button that seems to have done nothing.
enum _UpdateFrom { band, figures }

/// What the update button last said.
class _Notice {
  const _Notice(this.message, {required this.from, this.detail});

  final String message;

  /// Which control was pressed.
  final _UpdateFrom from;

  /// The server's reason, when the update did not start.
  final String? detail;
}

/// The costs of one organization.
class CostsScreen extends StatefulWidget {
  const CostsScreen({
    super.key,
    required this.repository,
    required this.organizationId,
  });

  final CostRepository repository;

  /// The organization to read. The caller has already shown the account is an
  /// administrator of a collection in it.
  final String organizationId;

  @override
  State<CostsScreen> createState() => _CostsScreenState();
}

class _CostsScreenState extends State<CostsScreen> {
  late final List<String> _months = costMonthChoices(costNow());
  late String _month = _months.first;
  CostReport? _report;
  ApiFailure? _failure;

  /// Counts the loads, so an answer for a month the reviewer has moved on from
  /// is dropped rather than drawn.
  int _generation = 0;
  bool _refreshing = false;
  _Notice? _notice;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  /// Reads [_month]. A quiet load keeps the figures on screen until the new
  /// ones arrive, for a change the reviewer made themselves.
  Future<void> _load({bool quiet = false}) async {
    final int generation = ++_generation;
    if (!quiet) {
      setState(() {
        _report = null;
        _failure = null;
      });
    }
    try {
      final CostReport report = await widget.repository.costs(
        widget.organizationId,
        from: _month,
        to: _month,
      );
      if (!mounted || generation != _generation) return;
      setState(() {
        _report = report;
        _failure = null;
      });
    } on ApiFailure catch (failure) {
      if (!mounted || generation != _generation) return;
      setState(() {
        _report = null;
        _failure = failure;
      });
    }
  }

  void _choose(String month) {
    if (month == _month) return;
    setState(() {
      _month = month;
      _notice = null;
    });
    unawaited(_load());
  }

  Future<void> _refresh(_UpdateFrom from) async {
    if (_refreshing) return;
    setState(() {
      _refreshing = true;
      _notice = null;
    });
    _Notice notice;
    try {
      final bool started = await widget.repository.refreshCosts(
        widget.organizationId,
      );
      notice = _Notice(
        started
            ? CostsScreenCopy.refreshStarted
            : CostsScreenCopy.refreshNotStarted,
        from: from,
      );
    } on ApiFailure catch (failure) {
      notice = _Notice(
        CostsScreenCopy.refreshFailed,
        from: from,
        detail: failure.message,
      );
    }
    if (!mounted) return;
    setState(() {
      _refreshing = false;
      _notice = notice;
    });
    // Once, from the event. The words are also on screen, but not in a live
    // region, so pressing the button a second time is heard a second time.
    AnnounceOnce.send(context, notice.message);
  }

  Future<void> _editLimit({
    required String subject,
    required String? collectionId,
    required CostLimit? current,
  }) async {
    final CostLimitResult? result = await showAdaptiveModal<CostLimitResult>(
      context,
      title: CostLimitCopy.title,
      body: (BuildContext _) => CostLimitForm(
        subject: subject,
        current: current,
        apply: (int? micros) => widget.repository.setCostLimit(
          widget.organizationId,
          collectionId: collectionId,
          micros: micros,
        ),
      ),
    );
    if (result == null || !mounted) return;
    AnnounceOnce.send(
      context,
      result == CostLimitResult.saved
          ? CostLimitCopy.savedFor(subject)
          : CostLimitCopy.removedFor(subject),
    );
    await _load(quiet: true);
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final UiLayoutMetrics layout = UiLayoutMetrics.fromConstraints(
          constraints,
          textScaler: MediaQuery.textScalerOf(context),
        );
        // A reading column, centred, with the page's gutter as its least edge.
        final double side = math.max(
          layout.gutter,
          (layout.width - layout.readableMax) / 2,
        );
        return CustomScrollView(
          slivers: <Widget>[
            SliverPadding(
              padding: EdgeInsetsDirectional.fromSTEB(
                side,
                ui.space.s4,
                side,
                0,
              ),
              // One block rather than a lazy list. The page is a few dozen
              // rows at most, and a sliver list marks its children as
              // repeated items, which the tiles' panes must not be (09
              // section 3.3).
              sliver: SliverToBoxAdapter(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[_monthSelect(), ..._body(context, ui)],
                ),
              ),
            ),
            SliverToBoxAdapter(
              child: SizedBox(
                height: ui.space.s8 + UiScaffold.of(context).bottomInset,
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _monthSelect() => UiSelect<String>(
    label: CostsScreenCopy.monthLabel,
    placeholder: CostsScreenCopy.monthPlaceholder,
    helpText: CostsScreenCopy.monthHelp,
    value: _month,
    options: <UiSelectOption<String>>[
      for (final String month in _months)
        UiSelectOption<String>(value: month, label: costMonthLabel(month)),
    ],
    onChanged: _choose,
  );

  /// Everything under the month: a failure, a wait, or the figures.
  List<Widget> _body(BuildContext context, UiThemeData ui) {
    final ApiFailure? failure = _failure;
    final CostReport? report = _report;
    if (failure != null) {
      return <Widget>[SizedBox(height: ui.space.s6), _failureState(failure)];
    }
    if (report == null) {
      return <Widget>[
        SizedBox(height: ui.space.s6),
        // Keyed by the month, so choosing another announces its own wait.
        LoadingAnnouncement(
          key: ValueKey<String>('costs-loading-$_month'),
          thing: CostsScreenCopy.loadingThing(costMonthLabel(_month)),
        ),
        const UiSkeleton.tile(),
        SizedBox(height: ui.space.s6),
        const UiSkeleton.row(),
        const UiSkeleton.row(),
        const UiSkeleton.row(),
      ];
    }
    return _figures(ui, report);
  }

  Widget _failureState(ApiFailure failure) {
    final bool unavailable = failure.code == CostsScreenCopy.unavailableCode;
    final bool forbidden = failure.status == 403;
    // Retrying cannot turn a meter on or make an account an administrator, so
    // those two offer no button (07 section 13, states).
    final bool retryable = !unavailable && !forbidden;
    return Announcer(
      child: UiEmptyState(
        icon: forbidden ? UiIcons.locked : UiIcons.syncProblem,
        title: unavailable
            ? CostsScreenCopy.unavailableTitle
            : forbidden
            ? CostsScreenCopy.forbiddenTitle
            : CostsScreenCopy.notLoadedTitle,
        body: unavailable
            ? CostsScreenCopy.unavailableBody
            : forbidden
            ? CostsScreenCopy.forbiddenBody
            : failure.message,
        action: retryable
            ? UiButton(
                label: CostsScreenCopy.retry,
                onPressed: () => unawaited(_load()),
              )
            : null,
      ),
    );
  }

  List<Widget> _figures(UiThemeData ui, CostReport report) {
    final String monthName = costMonthLabel(_month);
    final CostMonth? month = report.monthOf(_month);
    final List<CostStage> stages = month?.stagesByCost ?? const <CostStage>[];
    final List<CostModelRow> models = report.modelsOf(_month);
    final CostMeter? meter = report.meter;
    return <Widget>[
      ..._meterBanner(ui, meter),
      SizedBox(height: ui.space.s6),
      _heading(ui, CostsScreenCopy.organizationHeading),
      SizedBox(height: ui.space.s2),
      _organization(ui, report, monthName),
      SizedBox(height: ui.space.s6),
      _heading(ui, CostsScreenCopy.organizationLimitHeading),
      SizedBox(height: ui.space.s2),
      ..._organizationLimit(ui, report),
      SizedBox(height: ui.space.s6),
      _heading(ui, CostsScreenCopy.collectionsHeading),
      SizedBox(height: ui.space.s2),
      ..._collections(ui, report),
      SizedBox(height: ui.space.s6),
      _heading(ui, CostsScreenCopy.stagesHeading),
      SizedBox(height: ui.space.s2),
      if (stages.isEmpty)
        _absence(ui, CostsScreenCopy.noCosts)
      else
        for (final CostStage stage in stages) _stageRow(ui, stage),
      SizedBox(height: ui.space.s6),
      _heading(ui, CostsScreenCopy.modelsHeading),
      SizedBox(height: ui.space.s2),
      if (models.isEmpty)
        _absence(ui, CostsScreenCopy.noCosts)
      else
        for (final CostModelRow row in models) _modelRow(ui, row),
      SizedBox(height: ui.space.s6),
      _heading(ui, CostsScreenCopy.figuresHeading),
      SizedBox(height: ui.space.s2),
      ..._freshness(ui, report),
    ];
  }

  Widget _heading(UiThemeData ui, String text) =>
      UiSectionHeader(title: text, role: UiSectionHeaderRole.card);

  /// A slice the meter recorded nothing for: words, in the place a figure
  /// would be.
  Widget _absence(UiThemeData ui, String text) => Semantics(
    container: true,
    child: Text(
      text,
      style: ui.type.body.copyWith(color: ui.color.inkSecondary),
    ),
  );

  /// Shown above the figures when the meter says they may be incomplete.
  List<Widget> _meterBanner(UiThemeData ui, CostMeter? meter) {
    final String? through = meter?.allocatedThrough;
    final (String, String?)? words = switch (meter?.allocation) {
      CostAllocation.behind => (
        CostsScreenCopy.behindTitle,
        CostsScreenCopy.behindDetail(
          through == null ? null : costDayLabel(through),
        ),
      ),
      CostAllocation.neverRun => (CostsScreenCopy.neverRunTitle, null),
      _ => null,
    };
    if (words == null) return const <Widget>[];
    return <Widget>[
      SizedBox(height: ui.space.s4),
      UiBanner(
        message: words.$1,
        detail: words.$2,
        tone: UiBannerTone.needsReview,
      ),
      SizedBox(height: ui.space.s2),
      // A button under the band rather than the band's own action: a band's
      // action has no busy state, and the update takes a moment. It is busy
      // while the request runs, and its outcome is written under it.
      _updateControl(ui, _UpdateFrom.band),
    ];
  }

  /// "Update figures", busy while the request is out, and what it answered
  /// beneath it when it was this control that was pressed.
  Widget _updateControl(UiThemeData ui, _UpdateFrom from) {
    final _Notice? notice = _notice?.from == from ? _notice : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: CostsScreenCopy.refreshLabel,
            busyLabel: CostsScreenCopy.refreshBusy,
            variant: UiButtonVariant.secondary,
            leading: UiIcons.reload,
            loading: _refreshing,
            onPressed: _refreshing ? null : () => unawaited(_refresh(from)),
          ),
        ),
        if (notice != null) ...<Widget>[
          SizedBox(height: ui.space.s4),
          if (notice.detail == null)
            Text(
              notice.message,
              style: ui.type.body.copyWith(color: ui.color.inkSecondary),
            )
          else
            UiBanner(
              message: notice.message,
              detail: notice.detail,
              tone: UiBannerTone.blocked,
            ),
        ],
      ],
    );
  }

  /// A numeral tile that reads its line under the numeral too. The tile's own
  /// node drops everything inside it, and the line is what says what the
  /// number is (after which allowance, held for what), so it is said here.
  Widget _tile({
    required String label,
    required String value,
    required String footer,
    bool hero = false,
  }) => UiDataTile(
    label: label,
    value: value,
    footer: footer,
    hero: hero,
    semanticsLabel: '$label, $value. $footer',
  );

  Widget _organization(UiThemeData ui, CostReport report, String monthName) {
    final CostAmounts totals = report.totals;
    if (!totals.hasCosts) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Semantics(
            container: true,
            child: Text(
              CostsScreenCopy.noCosts,
              style: ui.type.title.copyWith(color: ui.color.ink),
            ),
          ),
          SizedBox(height: ui.space.s1),
          Text(
            CostsScreenCopy.noCostsBody(monthName),
            style: ui.type.body.copyWith(color: ui.color.inkSecondary),
          ),
        ],
      );
    }
    return _TileGrid(
      tiles: <Widget>[
        _tile(
          label: CostsScreenCopy.costLabel(monthName),
          value: formatMicros(totals.costMicros),
          footer: CostsScreenCopy.costFooter,
          hero: true,
        ),
        _tile(
          label: CostsScreenCopy.heldLabel,
          value: formatMicros(totals.heldMicros),
          footer: totals.heldMicros != 0
              ? CostsScreenCopy.heldFooter
              : CostsScreenCopy.heldNoneFooter,
        ),
        _tile(
          label: CostsScreenCopy.listCostLabel,
          value: formatMicros(totals.listCostMicros),
          footer: CostsScreenCopy.listCostFooter,
        ),
      ],
    );
  }

  List<Widget> _organizationLimit(UiThemeData ui, CostReport report) {
    final CostLimit? limit = report.organizationLimit;
    if (report.capsUnavailable) {
      // The limits are all null because they could not be read, not because
      // none is set: say so, and offer neither "Set limit" nor "Change limit"
      // over a limit that cannot be seen.
      return <Widget>[
        _absence(ui, CostsScreenCopy.limitsUnreadable),
        SizedBox(height: ui.space.s2),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: UiButton(
            label: CostsScreenCopy.retry,
            variant: UiButtonVariant.secondary,
            leading: UiIcons.reload,
            onPressed: () => unawaited(_load(quiet: true)),
          ),
        ),
      ];
    }
    final Widget action = Align(
      alignment: AlignmentDirectional.centerStart,
      child: UiButton(
        label: limit == null
            ? CostsScreenCopy.setLimit
            : CostsScreenCopy.changeLimit,
        variant: UiButtonVariant.secondary,
        leading: UiIcons.edit,
        onPressed: () => unawaited(
          _editLimit(
            subject: CostsScreenCopy.organizationSubject,
            collectionId: null,
            current: limit,
          ),
        ),
      ),
    );
    if (limit == null) {
      return <Widget>[
        _absence(ui, CostsScreenCopy.noOrganizationLimit),
        SizedBox(height: ui.space.s2),
        action,
      ];
    }
    return <Widget>[
      _tile(
        label: CostsScreenCopy.leftLabel(limit.month),
        value: limit.reached
            ? CostsScreenCopy.limitReachedValue
            : formatMicros(limit.remainingMicros),
        footer: CostsScreenCopy.limitFooter(limit),
      ),
      SizedBox(height: ui.space.s2),
      action,
    ];
  }

  List<Widget> _collections(UiThemeData ui, CostReport report) {
    final List<CostCollectionRow> rows = costCollectionRows(report.collections);
    if (rows.isEmpty) {
      return <Widget>[_absence(ui, CostsScreenCopy.noCollections)];
    }
    return <Widget>[
      for (final CostCollectionRow row in rows)
        _collectionRow(ui, row, report.capsUnavailable),
    ];
  }

  Widget _collectionRow(
    UiThemeData ui,
    CostCollectionRow row,
    bool limitsUnreadable,
  ) {
    final CostCollection collection = row.collection;
    final CostAmounts total = collection.total;
    final String cost = total.hasCosts
        ? formatMicros(total.costMicros)
        : CostsScreenCopy.noCosts;
    // A collection the server does not list has no name to show, and no limit
    // can be set for it: the service refuses an id that is not one of the
    // organization's collections. Its costs are still its costs, in words.
    final bool listed = collection.listed;
    final String name = collection.name ?? CostsScreenCopy.collectionNotListed;
    final bool editable = listed && !limitsUnreadable;
    final String? limit = !listed
        ? (collection.limit == null
              ? null
              : CostsScreenCopy.rowLimit(collection.limit))
        : limitsUnreadable
        ? CostsScreenCopy.rowLimitUnreadable
        : CostsScreenCopy.rowLimit(collection.limit);
    final String action = collection.limit == null
        ? CostsScreenCopy.setLimit
        : CostsScreenCopy.changeLimit;
    final String including = row.hasChildren && total.hasCosts
        ? ' ${CostsScreenCopy.includingSubCollections}'
        : '';
    return Padding(
      key: ValueKey<String>('cost-collection-${collection.id}'),
      // Sub-collections sit under their parent, one step in for each level.
      padding: EdgeInsetsDirectional.only(start: row.depth * ui.space.s4),
      child: UiListRow(
        title: name,
        subtitle: _detail(<String>[cost, ?limit]),
        semanticsLabel: editable
            ? '$name, $cost$including, $limit. $action'
            : <String>['$name, $cost$including', ?limit].join(', '),
        leading: const UiIcon(UiIcons.collection),
        // A limit that cannot be read cannot be changed from here: the form
        // would start from "no monthly limit" and write over one it never saw.
        trailing: editable
            ? UiRowTrailing(label: action, icon: UiIcons.edit)
            : null,
        onPressed: editable
            ? () => unawaited(
                _editLimit(
                  subject: collection.name!,
                  collectionId: collection.id,
                  current: collection.limit,
                ),
              )
            : null,
      ),
    );
  }

  Widget _stageRow(UiThemeData ui, CostStage stage) {
    final CostAmounts amounts = stage.amounts;
    final String name = costStageLabel(stage.stage);
    final String cost = formatMicros(amounts.costMicros);
    final String detail = _detail(<String>[
      CostsScreenCopy.entries(amounts.entries),
      if (amounts.heldMicros != 0) CostsScreenCopy.held(amounts.heldMicros),
    ]);
    return UiListRow(
      key: ValueKey<String>('cost-stage-${stage.stage}'),
      title: name,
      subtitle: detail,
      semanticsLabel: '$name, $cost, $detail',
      trailing: Text(cost, style: ui.type.title.copyWith(color: ui.color.ink)),
    );
  }

  Widget _modelRow(UiThemeData ui, CostModelRow row) {
    final CostAmounts amounts = row.amounts;
    final String cost = formatMicros(amounts.costMicros);
    final String detail = _detail(<String>[
      if (row.stage.isNotEmpty) costStageLabel(row.stage),
      if (row.provider.isNotEmpty) costProviderLabel(row.provider),
      CostsScreenCopy.entries(amounts.entries),
    ]);
    return UiListRow(
      key: ValueKey<String>(
        'cost-model-${row.stage}-${row.provider}-${row.resource}',
      ),
      title: row.resource,
      subtitle: detail,
      semanticsLabel: '${row.resource}, $cost, $detail',
      trailing: Text(cost, style: ui.type.title.copyWith(color: ui.color.ink)),
    );
  }

  /// Metadata values on one line, separated by the middle dot (02 section 6).
  String _detail(List<String> parts) => parts.join(' · ');

  List<Widget> _freshness(UiThemeData ui, CostReport report) {
    final DateTime? updated = report.updatedAt;
    final CostMeter? meter = report.meter;
    // The line under the update time: how far the costs are counted. The two
    // statuses that mean "incomplete" already have a banner above the figures,
    // and a status this client has not met is still named.
    String? counted;
    if (meter != null) {
      switch (meter.allocation) {
        case CostAllocation.ok:
          final String? day = meter.allocatedThrough;
          if (day != null) {
            counted = CostsScreenCopy.countedThrough(costDayLabel(day));
          }
        case CostAllocation.behind || CostAllocation.neverRun:
          break;
        case null:
          counted = CostsScreenCopy.countingStatus(meter.status);
      }
    }
    final TextStyle line = ui.type.body.copyWith(color: ui.color.ink);
    return <Widget>[
      Text(
        updated == null
            ? CostsScreenCopy.updatedUnknown
            : CostsScreenCopy.updated(absoluteTime(updated)),
        style: line,
      ),
      if (counted != null) ...<Widget>[
        SizedBox(height: ui.space.s1),
        Text(counted, style: line),
      ],
      SizedBox(height: ui.space.s4),
      _updateControl(ui, _UpdateFrom.figures),
    ];
  }
}

/// Tiles side by side where the width earns it, stacked where it does not.
///
/// The least a tile is given is four hit boxes, scaled with the reader's text,
/// so a larger type steps the row down to fewer columns instead of squeezing
/// the numerals.
class _TileGrid extends StatelessWidget {
  const _TileGrid({required this.tiles});

  final List<Widget> tiles;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double scale = math.max(
      1,
      MediaQuery.textScalerOf(context).scale(ui.space.s4) / ui.space.s4,
    );
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        final double gap = ui.space.s4;
        final double least = ui.space.labelMin * 2 * scale;
        final int columns = ((constraints.maxWidth + gap) / (least + gap))
            .floor()
            .clamp(1, tiles.length);
        final double width =
            (constraints.maxWidth - gap * (columns - 1)) / columns;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: <Widget>[
            for (final Widget tile in tiles)
              SizedBox(width: width, child: tile),
          ],
        );
      },
    );
  }
}
