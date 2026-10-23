import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';
import 'package:widgetbook/widgetbook.dart';
import '../story.dart';

const modalRecipeTypes = [
  '2FA code',
  'Access request',
  'Center aligned',
  'Centered photo',
  'Centered photo carousel',
  'Centered video carousel',
  'Checkboxes',
  'Date picker',
  'Destructive horizontal',
  'Destructive stacked left aligned',
  'Dropdown',
  'Email invite',
  'File upload',
  'Form 01',
  'Form 02',
  'Horizontal',
  'Horizontal fill container',
  'Horizontal left aligned',
  'Horizontal right aligned (checkbox)',
  'Image crop',
  'Input field',
  'Labels',
  'Left aligned',
  'Link field',
  'Log in',
  'Password prompt',
  'Payment details',
  'Payment details with image',
  'Payment method',
  'Plan 01',
  'Plan 02',
  'Profile settings',
  'Sign up 01',
  'Sign up 02',
  'Stacked left aligned',
  'Stacked with team',
  'Stacked with team and invites',
  'Stacked with team and link',
  'Toggles',
  'User invite',
  'User selection',
  'Verification code',
  'Vertical fill container',
  'Warning horizontal',
  'Warning stacked left aligned',
];
const drawerRecipeTypes = [
  'File upload',
  'Filters',
  'Labels',
  'Message chat',
  'Messages',
  'Notification settings button groups',
  'Notification settings checkboxes',
  'Notifications',
  'Order summary',
  'Payment details',
  'Payment method',
  'Placeholder',
  'Plan',
  'Project details',
  'Team members',
  'User profile',
];

List<WidgetbookComponent> get modalRecipeComponents => [
  WidgetbookComponent(
    name: 'Modal recipes',
    useCases: [
      for (final type in modalRecipeTypes)
        story(
          type,
          'A composed $type pattern using actual Specimen controls and local synthetic state. The host owns submission, validation, permissions and persistence.',
          (_) => _RecipePreview(type: type),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'Slideout recipes',
    useCases: [
      for (final type in drawerRecipeTypes)
        story(
          type,
          'A $type side panel with real controls, scrollable body and persistent actions. No service or transaction is performed by this example.',
          (_) => _RecipePreview(type: type, drawer: true),
        ),
    ],
  ),
  WidgetbookComponent(
    name: 'UiCropEditor',
    useCases: [
      story(
        'Controlled normalized region',
        'Drag the region, use arrow keys to move it, Shift+arrows to resize, or use the four named sliders. RTL does not reverse physical image coordinates. Applying a crop belongs to the host.',
        (_) => const _RecipeBody(type: 'Image crop'),
      ),
    ],
  ),
];

class _RecipePreview extends StatelessWidget {
  const _RecipePreview({required this.type, this.drawer = false});
  final String type;
  final bool drawer;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      ActionExample(
        builder: (context, report) => UiButton(
          label: 'Open $type',
          onPressed: () async {
            final future = drawer
                ? UiDrawer.show<bool>(
                    context: context,
                    title: type,
                    description: 'Synthetic collection workspace',
                    body: (_) => _RecipeBody(type: type),
                    footer: (context) => _actions(context),
                  )
                : UiModalPanel.show<bool>(
                    context: context,
                    semanticsLabel: type,
                    builder: (context) => UiModalPanel(
                      title: type,
                      description: 'Review the details before continuing.',
                      layout: type.toLowerCase().contains('center')
                          ? UiModalLayout.centered
                          : type.toLowerCase().contains('horizontal')
                          ? UiModalLayout.horizontal
                          : UiModalLayout.stacked,
                      leading: UiFeaturedIcon(
                        icon: type.contains('Destructive')
                            ? UiIcons.blocked
                            : type.contains('Warning')
                            ? UiIcons.needsReview
                            : UiIcons.record,
                        tone: type.contains('Destructive')
                            ? UiBannerTone.blocked
                            : type.contains('Warning')
                            ? UiBannerTone.needsReview
                            : UiBannerTone.info,
                      ),
                      onDismiss: () => Navigator.pop(context),
                      footer: _actions(context),
                      child: _RecipeBody(type: type),
                    ),
                  );
            final accepted = await future;
            if (context.mounted) {
              report(accepted == true ? '$type applied locally' : 'Cancelled');
            }
          },
        ),
      ),
      SizedBox(height: context.ui.space.s4),
      _RecipeBody(type: type),
    ],
  );
  Widget _actions(BuildContext context) => _RecipeActions(type: type);
}

class _RecipeActions extends StatefulWidget {
  const _RecipeActions({required this.type});
  final String type;
  @override
  State<_RecipeActions> createState() => _RecipeActionsState();
}

class _RecipeActionsState extends State<_RecipeActions> {
  bool remember = false;
  @override
  Widget build(BuildContext context) {
    final primary = UiButton(
      label: 'Apply locally',
      onPressed: () => Navigator.pop(context, true),
    );
    final cancel = UiButton(
      label: 'Cancel',
      variant: UiButtonVariant.secondary,
      onPressed: () => Navigator.pop(context, false),
    );
    final gap = context.ui.space.s2;
    final type = widget.type.toLowerCase();
    final actions = UiButtonRow(primary: primary, secondary: cancel);
    if (type.contains('vertical fill')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          primary,
          SizedBox(height: gap),
          cancel,
        ],
      );
    }
    if (type.contains('horizontal fill')) {
      return LayoutBuilder(
        builder: (context, constraints) {
          if (constraints.maxWidth <
              primary.intrinsicWidth(context) +
                  cancel.intrinsicWidth(context) +
                  gap) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                primary,
                SizedBox(height: gap),
                cancel,
              ],
            );
          }
          return Row(
            children: [
              Expanded(child: cancel),
              SizedBox(width: gap),
              Expanded(child: primary),
            ],
          );
        },
      );
    }
    if (type.contains('horizontal left')) {
      return Align(
        alignment: AlignmentDirectional.centerStart,
        child: Wrap(spacing: gap, runSpacing: gap, children: [cancel, primary]),
      );
    }
    if (type.contains('right aligned (checkbox)')) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          UiCheckbox(
            label: 'Remember this preference',
            value: remember,
            onChanged: (value) => setState(() => remember = value),
          ),
          SizedBox(height: gap),
          actions,
        ],
      );
    }
    return actions;
  }
}

class _RecipeBody extends StatefulWidget {
  const _RecipeBody({required this.type});
  final String type;
  @override
  State<_RecipeBody> createState() => _RecipeBodyState();
}

class _RecipeBodyState extends State<_RecipeBody> {
  bool checked = false, playing = false;
  Set<String> selected = {'reader'};
  List<String> tags = ['collection'];
  String code = '', role = 'reader';
  DateTime? date = DateTime.utc(2026, 10, 22);
  int page = 0, nextFileId = 0;
  final notificationPreferences = <String>{};
  String filterQuery = '';
  final filters = <String>{'Needs review'};
  Rect crop = const Rect.fromLTWH(.15, .15, .7, .7);
  Duration position = Duration.zero;
  List<UiUploadFile> files = [];
  final List<String> messages = [];
  final draft = TextEditingController();
  final shareLink = TextEditingController(
    text: 'https://example.org/collection',
  );
  @override
  void dispose() {
    draft.dispose();
    shareLink.dispose();
    super.dispose();
  }

  void _setNotification(String label, bool value) => setState(() {
    if (value) {
      notificationPreferences.add(label);
    } else {
      notificationPreferences.remove(label);
    }
  });
  Widget _art(String label) => Container(
    color: context.ui.color.paper,
    padding: EdgeInsets.all(context.ui.space.s4),
    child: Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Flexible(
            child: FittedBox(
              child: UiMark(label: 'Specimen artwork', size: 64),
            ),
          ),
          SizedBox(height: context.ui.space.s3),
          Flexible(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(label, textAlign: TextAlign.center),
            ),
          ),
        ],
      ),
    ),
  );
  Widget _choices({
    bool plans = false,
    bool users = false,
    bool payments = false,
  }) => UiSelectionCards<String>(
    label: plans
        ? 'Choose a plan'
        : users
        ? 'Choose team members'
        : payments
        ? 'Payment method'
        : 'Access level',
    selected: selected,
    mode: users ? UiSelectionMode.multiple : UiSelectionMode.single,
    onChanged: (value) => setState(() => selected = value),
    options: [
      UiSelectionCardOption(
        value: 'reader',
        label: plans
            ? 'Research'
            : users
            ? 'Maya Chen'
            : payments
            ? 'Visa ending in 4242'
            : 'Can view',
        supporting: plans
            ? 'For one research team'
            : users
            ? 'Collection manager'
            : payments
            ? 'Expires 12/2028'
            : 'Read collection records',
        leading: users
            ? const UiAvatar(name: 'Maya Chen')
            : payments
            ? const UiPaymentMark(name: 'Visa')
            : const UiIcon(UiIcons.record),
      ),
      UiSelectionCardOption(
        value: 'editor',
        label: plans
            ? 'Collections'
            : users
            ? 'Alex Rivera'
            : payments
            ? 'Bank transfer'
            : 'Can edit',
        supporting: plans
            ? 'For multiple collection teams'
            : users
            ? 'Researcher'
            : payments
            ? 'Add bank details in the host flow'
            : 'Review and edit collection records',
        leading: users
            ? const UiAvatar(name: 'Alex Rivera')
            : payments
            ? const UiPaymentMark(name: 'Bank')
            : const UiIcon(UiIcons.collection),
      ),
    ],
  );
  Widget _fields(List<String> labels) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      for (final label in labels)
        Padding(
          padding: EdgeInsets.only(bottom: context.ui.space.s3),
          child: UiField(
            label: label,
            keyboardType: label.toLowerCase().contains('email')
                ? TextInputType.emailAddress
                : TextInputType.text,
          ),
        ),
    ],
  );
  @override
  Widget build(BuildContext context) {
    final type = widget.type.toLowerCase();
    final ui = context.ui;
    if (type.contains('image crop')) {
      return UiCropEditor(
        image: _art('Original brand artwork'),
        value: crop,
        onChanged: (value) => setState(() => crop = value),
      );
    }
    if (type.contains('carousel')) {
      final carousel = UiCarousel(
        index: page,
        onChanged: (value) => setState(() {
          page = value;
          position = Duration.zero;
          playing = false;
        }),
        label: 'Collection media',
        children: [
          for (var i = 0; i < 3; i++) _art('Collection artwork ${i + 1}'),
        ],
      );
      return type.contains('video')
          ? UiMediaPlayer(
              title: 'Collection video ${page + 1}',
              position: position,
              duration: const Duration(minutes: 2),
              playing: playing,
              onPlayingChanged: (value) => setState(() => playing = value),
              onSeek: (value) => setState(() => position = value),
              child: carousel,
            )
          : carousel;
    }
    if (type.contains('photo')) {
      return AspectRatio(
        aspectRatio: 4 / 3,
        child: _art('Collection image preview slot'),
      );
    }
    if (type.contains('code')) {
      return UiVerificationCode(
        label: 'Verification code',
        value: code,
        length: type.contains('2fa') ? 6 : 4,
        onChanged: (value) => setState(() => code = value),
        helpText: 'Example only; no code is sent.',
      );
    }
    if (type.contains('date')) {
      return UiDatePicker(
        label: 'Review date',
        value: date,
        firstDate: DateTime.utc(2026, 1),
        lastDate: DateTime.utc(2027, 12, 31),
        onChanged: (value) => setState(() => date = value),
      );
    }
    if (type.contains('upload')) {
      return UiFileUpload(
        label: 'Collection files',
        files: files,
        chooseLabel: 'Add synthetic file',
        onChooseFiles: () => setState(
          () => files = [
            ...files,
            UiUploadFile(
              id: '${nextFileId++}',
              name: 'specimen-$nextFileId.jpg',
              statusLabel: 'Queued',
              detail: 'Synthetic example',
            ),
          ],
        ),
        onRemove: (file) => setState(
          () => files = files.where((f) => f.id != file.id).toList(),
        ),
      );
    }
    if (type.contains('payment method')) return _choices(payments: true);
    if (type.contains('payment details')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (type.contains('with image')) ...[
            AspectRatio(
              aspectRatio: 16 / 9,
              child: _art('Collection workspace plan'),
            ),
            SizedBox(height: ui.space.s4),
          ],
          const UiPaymentMark(name: 'Card'),
          SizedBox(height: ui.space.s3),
          _fields([
            'Name on card',
            'Card number',
            'Expiry date',
            'Security code',
          ]),
          const Text('Synthetic form. No payment data is transmitted.'),
        ],
      );
    }
    if (type.contains('plan')) return _choices(plans: true);
    if (type.contains('order summary')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('Collection workspace'),
          const Text('Research plan · 1 team'),
          SizedBox(height: ui.space.s4),
          const UiField(label: 'Promotion code'),
          SizedBox(height: ui.space.s4),
          const Text('Example total: \$0.00'),
          const Text('Synthetic presentation. No purchase is made.'),
        ],
      );
    }
    if (type.contains('notification settings button')) {
      return UiButtonGroup(
        label: 'Notification delivery',
        items: [
          UiButtonGroupItem(
            label: 'All',
            selected: role == 'reader',
            onPressed: () => setState(() => role = 'reader'),
          ),
          UiButtonGroupItem(
            label: 'Mentions',
            selected: role == 'editor',
            onPressed: () => setState(() => role = 'editor'),
          ),
        ],
      );
    }
    if (type.contains('toggles') ||
        type.contains('notification settings check')) {
      return Column(
        children: [
          for (final label in [
            'Collection updates',
            'Mentions',
            'Review assignments',
          ])
            type.contains('checkbox')
                ? UiCheckbox(
                    label: label,
                    value: notificationPreferences.contains(label),
                    onChanged: (value) => _setNotification(label, value),
                  )
                : UiSwitch(
                    label: label,
                    value: notificationPreferences.contains(label),
                    onChanged: (value) => _setNotification(label, value),
                  ),
        ],
      );
    }
    if (type == 'checkboxes' || type.contains('filters')) {
      const groups = {
        'Review status': ['Needs review', 'In progress', 'Reviewed'],
        'Record details': [
          'Images available',
          'Has catalogue number',
          'Has location',
          'Has collector',
        ],
      };
      final matches = groups.values
          .expand((v) => v)
          .where(
            (label) => label.toLowerCase().contains(filterQuery.toLowerCase()),
          )
          .toList();
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          UiSearchField(
            label: 'Search options',
            clearLabel: 'Clear option search',
            onChanged: (v) => setState(() => filterQuery = v),
          ),
          SizedBox(height: ui.space.s3),
          Wrap(
            spacing: ui.space.s2,
            runSpacing: ui.space.s2,
            children: [
              UiButton(
                label: 'Saved: Needs review',
                variant: UiButtonVariant.secondary,
                onPressed: () => setState(() {
                  filters.clear();
                  filters.add('Needs review');
                }),
              ),
              UiButton(
                label: 'Clear filters',
                variant: UiButtonVariant.ghost,
                onPressed: () => setState(filters.clear),
              ),
            ],
          ),
          for (final group in groups.entries)
            if (group.value.any(matches.contains)) ...[
              SizedBox(height: ui.space.s4),
              Semantics(
                header: true,
                child: Text(group.key, style: ui.type.title),
              ),
              for (final label in group.value.where(matches.contains))
                UiCheckbox(
                  label: label,
                  value: filters.contains(label),
                  onChanged: (v) => setState(() {
                    if (v) {
                      filters.add(label);
                    } else {
                      filters.remove(label);
                    }
                  }),
                ),
            ],
          if (matches.isEmpty) const Text('No matching options'),
          SizedBox(height: ui.space.s3),
          Text('${filters.length} filters selected'),
        ],
      );
    }
    if (type.contains('labels')) {
      return UiTagField(
        label: 'Collection labels',
        values: tags,
        onChanged: (value) => setState(() => tags = value),
      );
    }
    if (type.contains('message')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const UiMessage(
            author: 'Maya Chen',
            body: 'The specimen is ready for review.',
            timeLabel: '2 minutes ago',
          ),
          for (final message in messages)
            UiMessage(
              author: 'You',
              body: message,
              timeLabel: 'Just now',
              outgoing: true,
            ),
          UiMessageComposer(
            controller: draft,
            onSend: (message) async {
              setState(() => messages.add(message));
            },
          ),
        ],
      );
    }
    if (type == 'notifications') {
      return Column(
        children: [
          for (final title in [
            'New source evidence',
            'Review assigned',
            'Export ready',
          ])
            UiNotice(
              title: title,
              description: 'A collection activity update.',
              timestamp: '2 minutes ago',
              leading: const UiAvatar(name: 'Maya Chen'),
            ),
        ],
      );
    }
    if (type.contains('user selection') || type.contains('team members')) {
      return _choices(users: true);
    }
    if (type.contains('user profile') || type.contains('profile settings')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const UiAvatar(name: 'Maya Chen'),
          _fields(['Display name', 'Email address', 'Role']),
          UiSwitch(
            label: 'Available for review',
            value: checked,
            onChanged: (value) => setState(() => checked = value),
          ),
        ],
      );
    }
    if (type.contains('team')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _choices(users: true),
          if (type.contains('invite'))
            UiTagField(
              label: 'Invite email addresses',
              values: tags,
              onChanged: (value) => setState(() => tags = value),
            ),
          if (type.contains('link'))
            UiField(label: 'Share link', controller: shareLink, readOnly: true),
        ],
      );
    }
    if (type.contains('invite')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          UiTagField(
            label: 'Invite email addresses',
            values: tags,
            onChanged: (value) => setState(() => tags = value),
          ),
          _choices(),
        ],
      );
    }
    if (type.contains('log in') || type.contains('sign up')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (type.contains('sign up')) const UiField(label: 'Full name'),
          const UiField(
            label: 'Email address',
            keyboardType: TextInputType.emailAddress,
          ),
          const UiField(label: 'Password', obscureText: true),
          if (type.contains('sign up'))
            UiCheckbox(
              label: 'Keep me informed about collection updates',
              value: checked,
              onChanged: (value) => setState(() => checked = value),
            ),
        ],
      );
    }
    if (type.contains('password')) {
      return const UiField(label: 'Current password', obscureText: true);
    }
    if (type.contains('dropdown')) {
      return UiSelect<String>(
        label: 'Collection access',
        value: role,
        placeholder: 'Choose access',
        options: const [
          UiSelectOption(value: 'reader', label: 'Can view'),
          UiSelectOption(value: 'editor', label: 'Can edit'),
        ],
        onChanged: (value) => setState(() => role = value),
      );
    }
    if (type.contains('link field')) {
      return const UiField(
        label: 'Collection link',
        prefixText: 'https://',
        hintText: 'example.org/collection',
      );
    }
    if (type.contains('input field')) {
      return const UiField(
        label: 'Collection name',
        hintText: 'Enter a collection name',
      );
    }
    if (type.contains('form') ||
        type.contains('project') ||
        type.contains('access request')) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _fields(['Name', 'Email address']),
          const UiTextArea(label: 'Description'),
          if (type.contains('02')) _choices(),
        ],
      );
    }
    if (type.contains('destructive')) {
      return const UiNotice(
        title: 'Remove this draft?',
        description:
            'The host must explain the actual consequence and own the destructive action.',
        tone: UiBannerTone.blocked,
      );
    }
    if (type.contains('warning')) {
      return const UiNotice(
        title: 'Review before continuing',
        description:
            'Some records are incomplete. Check the collection details before applying changes.',
        tone: UiBannerTone.needsReview,
      );
    }
    if (type.contains('placeholder')) {
      return const UiEmptyState(
        title: 'Your content goes here',
        icon: UiIcons.record,
        body:
            'An intentional empty composition slot for a host-provided panel.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text('The collection changes are ready to review.'),
        SizedBox(height: ui.space.s3),
        if (type.contains('checkbox'))
          UiCheckbox(
            label: 'Do not show this again',
            value: checked,
            onChanged: (value) => setState(() => checked = value),
          )
        else
          const Text(
            'Review the supporting information before applying changes.',
          ),
      ],
    );
  }
}
